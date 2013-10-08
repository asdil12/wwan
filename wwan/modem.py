#!/usr/bin/env python2

import logging
import sys
import re
import os

from gsmmodem.util import *
from gsmmodem.exceptions import *
from gsmmodem.serial_comms import SerialComms

from .constants import *


logger = logging.getLogger('wwan')
loglevel = logging.DEBUG if True else logging.INFO
logger.setLevel(loglevel)
if False:
	loghandler = logging.handlers.SysLogHandler(address = '/dev/log')
else:
	loghandler = logging.StreamHandler(sys.stdout)
	formatter = logging.Formatter('[%(asctime)s] %(levelname)+8s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
	loghandler.setFormatter(formatter)
logger.addHandler(loghandler)


class WWANModem(SerialComms):
	CM_ERROR_REGEX = re.compile(r'^\+(CM[ES]) ERROR: (\d+)$')

	def __init__(self, port, baudrate=115200, interface='wwan0'):
		super(WWANModem, self).__init__(port, baudrate)
		# Used for parsing AT command errors
		log = logging.getLogger('wwan')
		self.interface = interface
		self._writeWait = 0 # Time (in seconds to wait after writing a command (adjusted when 515 errors are detected)
		self.connect()
		self.write('ATE0') # echo off

	def unlock_sim(self, pin):
		""" Unlocks the SIM card using the specified PIN (if necessary, else does nothing) """
		# Unlock the SIM card if needed
		if not self.sim_unlocked:
			if pin != None:
				return self.write('AT+CPIN="%s"' % pin)
			else:
				raise PinRequiredError('AT+CPIN')

	@property
	def sim_unlocked(self):
		return self.write('AT+CPIN?')[0] == '+CPIN: READY'

	@property
	def aquired_radio_technology(self):
		technologies = {
			'0,1,0': GPRS,
			'0,2,0': EDGE,
			'0,0,1': UMTS,
			'0,0,2': HSPA,
		}
		try:
			erinfoMatch = lineMatching(r'^\*ERINFO: (\d,\d,\d)$', self.write('AT*ERINFO?'))
			if erinfoMatch:
				return technologies[erinfoMatch.group(1)]
		except CommandError:
			return NONE

	@property
	def requested_radio_technology(self):
		technologies = {
			0: ERROR,
			1: PREFER_UMTS,
			4: OFF,
			5: FORCE_GPRS,
			6: FORCE_UMTS,
		}
		return technologies[int(lineStartingWith('+CFUN:', self.write('AT+CFUN?'))[7:])]
	@requested_radio_technology.setter
	def requested_radio_technology(self, value):
		technologies = {
			PREFER_UMTS: 1,
			OFF: 4,
			FORCE_GPRS: 5,
			FORCE_UMTS: 6,
		}
		self.write('AT+CFUN=%i' % technologies[value])

	@property
	def signal_strength(self):
		return int(lineStartingWith('+CIND:', self.write('AT+CIND?'))[9:10])

	@property
	def network_name(self):
		""" @return: the name of the GSM Network Operator to which the modem is connected """
		copsMatch = lineMatching(r'^\+COPS: (\d),(\d),"(.+)",\d\s?$', self.write('AT+COPS?'))
		# response format: +COPS: mode,format,"operator_name",x
		if copsMatch:
			return copsMatch.group(3)

	@property
	def network_registration(self):
		regs = {
			0: NOT_SEARCHING, # Not searching for network
			1: REG_HOME,      # Registered, home
			2: SEARCHING,     # Searching for network
			3: REG_DENIED,    # Registration denied
			4: SEARCHING,     # Out of range
			5: REG_ROAMING,   # Registered, roaming
		}
		try:
			cregMatch = lineMatching(r'^\+CREG:\s*(\d),(\d)$', self.write('AT+CREG?'))
			if cregMatch:
				return regs[int(cregMatch.group(2))]
		except CommandError:
			return NOT_SEARCHING

	@property
	def apn(self):
		cgdcontMatch = lineMatching(r'^\+CGDCONT:\s*(\d),"(IP|IPV6)","([^"]*)".*$', self.write('AT+CGDCONT?'))
		if cgdcontMatch:
			return cgdcontMatch.group(3)
	@apn.setter
	def apn(self, value):
		self.write('AT+CGDCONT=1,"%s","%s"' % ('IP' if self.ipver == 4 else 'IPV6', value))

	@property
	def ipver(self):
		"""
			IP  : IPv4 (4)
			IPV6: IPv6 (6)
		"""
		cgdcontMatch = lineMatching(r'^\+CGDCONT:\s*(\d),"(IP|IPV6)","([^"]*)".*$', self.write('AT+CGDCONT?'))
		if cgdcontMatch:
			return 4 if cgdcontMatch.group(2) == 'IP' else 6
	@ipver.setter
	def ipver(self, value):
		self.write('AT+CGDCONT=1,"%s","%s"' % ('IP' if value == 4 else 'IPV6', self.apn))

	@property
	def carrier(self):
		# needs watchdog: when connected and no carrier: reconnect, dhcpcd
		try:
			cf = "/sys/class/net/%s/carrier" % self.interface
			if os.path.exists(cf):
				return int(open(cf).read().strip()) == 1
			else:
				return False
		except IOError:
			return False

	@property
	def connected(self):
		try:
			return lineStartingWith('*ENAP:', self.write('AT*ENAP?'))[7:] == '1'
		except CommandError:
			return False

	@connected.setter
	def connected(self, value):
		self.write('AT*ENAP=%s' % ('1,1' if value else '0'))

	@property
	def gps(self):
		return lineStartingWith('*E2GPSCTL:', self.write('AT*E2GPSCTL?'))[10:] == '1,1,1'
	@gps.setter
	def gps(self, value):
		# needs requested_radio_technology != OFF
		# gps off seems not to work - FIXME: because I had some bugs in my code
		self.write('AT*E2GPSCTL=%s' % ('1,1,1' if value else '0,1,0'))


	@property
	def manufacturer(self):
		""" @return: The modem's manufacturer's name """
		return self.write('AT+CGMI')[0]

	@property
	def model(self):
		""" @return: The modem's model name """
		return self.write('AT+CGMM')[0]

	@property
	def revision(self):
		""" @return: The modem's software revision, or None if not known/supported """
		try:
			return self.write('AT+CGMR')[0]
		except CommandError:
			return None

	@property
	def imei(self):
		""" @return: The modem's serial number (IMEI number) """
		return self.write('AT+CGSN')[0]

	@property
	def imsi(self):
		""" @return: The IMSI (International Mobile Subscriber Identity) of the SIM card. 
		             The PIN may need to be entered before reading the IMSI """
		return self.write('AT+CIMI')[0]


	def write(self, data, waitForResponse=True, timeout=5, parseError=True, writeTerm="\r\n", expectedResponseTermSeq=None):
		""" Write data to the modem
		
		This method adds the '\r\n' end-of-line sequence to the data parameter, and
		writes it to the modem
		
		@param data: Command/data to be written to the modem
		@type data: str
		@param waitForResponse: Whether this method should block and return the response from the modem or not
		@type waitForResponse: bool
		@param timeout: Maximum amount of time in seconds to wait for a response from the modem
		@type timeout: int
		@param parseError: If True, a CommandError is raised if the modem responds with an error (otherwise the response is returned as-is)
		@type parseError: bool
		@param writeTerm: The terminating sequence to append to the written data
		@type writeTerm: str
		@param expectedResponseTermSeq: The expected terminating sequence that marks the end of the modem's response (defaults to '\r\n')
		@type expectedResponseTermSeq: str

		@raise CommandError: if the command returns an error (only if parseError parameter is True)
		@raise TimeoutException: if no response to the command was received from the modem
		
		@return: A list containing the response lines from the modem, or None if waitForResponse is False
		@rtype: list
		"""
		self.log.debug('write: %s', data)
		data_send = data + writeTerm
		responseLines = SerialComms.write(self, data_send.encode(), waitForResponse=waitForResponse, timeout=timeout, expectedResponseTermSeq=expectedResponseTermSeq)
		if self._writeWait > 0: # Sleep a bit if required (some older modems suffer under load)            
			time.sleep(self._writeWait)
		if waitForResponse:
			cmdStatusLine = responseLines[-1]
			if parseError:
				if 'ERROR' in cmdStatusLine:
					cmErrorMatch = self.CM_ERROR_REGEX.match(cmdStatusLine)
					if cmErrorMatch:
						errorType = cmErrorMatch.group(1)
						errorCode = int(cmErrorMatch.group(2))
						if errorCode == 515 or errorCode == 14:
							# 515 means: "Please wait, init or command processing in progress."
							# 14 means "SIM busy"
							self._writeWait += 0.2 # Increase waiting period temporarily
							# Retry the command after waiting a bit
							self.log.debug('Device/SIM busy error detected; self._writeWait adjusted to %fs', self._writeWait)
							time.sleep(self._writeWait)
							result = self.write(data, waitForResponse, timeout, parseError, writeTerm, expectedResponseTermSeq)
							self.log.debug('self_writeWait set to 0.1 because of recovering from device busy (515) error')
							if errorCode == 515:
								self._writeWait = 0.1 # Set this to something sane for further commands (slow modem)
							else:
								self._writeWait = 0 # The modem was just waiting for the SIM card
							return result
						if errorType == 'CME':
							raise CmeError(data, int(errorCode))
						elif errorType == 'CMS':
							raise CmsError(data, int(errorCode))
						else:
							raise CommandError(data, errorType, int(errorCode))
					else:
						raise CommandError(data)
				elif cmdStatusLine == 'COMMAND NOT SUPPORT': # Some Huawei modems respond with this for unknown commands
					raise CommandError(data + '({0})'.format(cmdStatusLine))
			return responseLines

