#!/usr/bin/env python2

import os
import sys
import subprocess
import threading
import json
from time import sleep

from gsmmodem.exceptions import *
from wwan.constants import *
from wwan.modem import WWANModem

config = json.load(open("/etc/wwan.json"))

"""
config = {
	"wwan_interface": "wwan0",
	"ipver": 4,
	"apn": "internet",
	"pin": "0000",
	"usbid": "0bdb:1900"
}
"""

class WWANControl(object):
	def __init__(self):
		self.enabled = False
		self.dhcpcd = None
		self.watchdog = None
		self._watchdog_ip_detected = False

	def enable(self):
		self.rfkill(False)
		sys.stdout.write("Waiting for USB device ...")
		sys.stdout.flush()
		while not self.ready:
			sleep(0.5)
			sys.stdout.write('.')
			sys.stdout.flush()
		print " OK"
		self.modem = WWANModem(self.ports['wwan'], interface=config['wwan_interface'])
		# first command may fail due to device being not ready, yet
		sys.stdout.write("Unlocking SIM Card ...")
		sys.stdout.flush()
		while True:
			try:
				self.modem.unlock_sim(config['pin'])
				break
			except (CommandError, TimeoutException):
				sleep(0.5)
				sys.stdout.write('.')
				sys.stdout.flush()
		print " OK"
		sys.stdout.write("Configuring UMTS card ...")
		self.modem.apn = config['apn']
		sys.stdout.write('.')
		sys.stdout.flush()
		self.modem.ipver = config['ipver']
		sys.stdout.write('.')
		sys.stdout.flush()
		print " OK"
		sys.stdout.write("Connecting to network ...")
		sys.stdout.flush()
		self.modem.requested_radio_technology = PREFER_UMTS
		while not self.modem.network_registration in [REG_HOME, REG_ROAMING]:
			sleep(0.5)
			sys.stdout.write('.')
			sys.stdout.flush()
		while self.modem.aquired_radio_technology == NONE:
			sleep(0.5)
			sys.stdout.write('.')
			sys.stdout.flush()
		print " OK"
		#while not self.modem.connected:
		#	try:
		sys.stdout.write("Starting IP connection ...")
		sys.stdout.flush()
		self.modem.connected = True
		while not self.modem.connected:
			sleep(0.5)
			sys.stdout.write('.')
			sys.stdout.flush()
		print " OK"
		#	except CommandError:
		#		sleep(0.5)
		sys.stdout.write("Getting IP via DHCP ...")
		self.dhcp_client(True)
		self.carrier_watchdog(True)
		while not self.ip:
			sys.stdout.write('.')
			sys.stdout.flush()
			sleep(0.5)
		print " OK"
		self.enabled = True
	
	def disable(self):
		sys.stdout.write("Shutting down UMTS card ...")
		self.enabled = False
		sys.stdout.write('.')
		sys.stdout.flush()
		self.carrier_watchdog(False)
		sys.stdout.write('.')
		sys.stdout.flush()
		self.dhcp_client(False)
		sys.stdout.write('.')
		sys.stdout.flush()
		try:
			self.modem.connected = False
			self.modem.requested_radio_technology = OFF
		except:
			pass
		sys.stdout.write('.')
		sys.stdout.flush()
		self.modem = None
		self.rfkill(True)
		sys.stdout.write('.')
		sys.stdout.flush()
		print " OK"

	def restart(self):
		try:
			self.dhcp_client(False)
			self.modem.connected = False
		except CommandError:
			pass
		self.modem.connected = True
		self.dhcp_client(True)

	def dhcp_client(self, value):
		if value:
			self._watchdog_ip_detected = False
			self.dhcpcd = subprocess.Popen(["dhcpcd", "-qB", "--noipv4ll", config['wwan_interface']])
		elif self.dhcpcd:
			self.dhcpcd.terminate()
			self.dhcpcd = None

	def _watchdog(self):
		while not self.stop_watchdog.wait(1):
			if self.enabled:
				if not self.modem.carrier:
					self.restart()
				if self.ip:
					self._watchdog_ip_detected = True
				elif self._watchdog_ip_detected:
					# IP disappeared
					self.restart()

	def carrier_watchdog(self, value):
		if value:
			self.stop_watchdog = threading.Event()
			self.watchdog = threading.Thread(target=self._watchdog)
			self.watchdog.daemon = True
			self.watchdog.start()
		elif self.watchdog:
			self.stop_watchdog.set()
			self.watchdog.join()

	def rfkill(self, value):
		return subprocess.call(["rfkill", "block" if value else "unblock", "wwan"],
			stdout=open("/dev/null", "w"), stderr=subprocess.STDOUT) == 0
		
	@property
	def ready(self):
		return subprocess.call(["lsusb", "-d", config['usbid']], stdout=open("/dev/null", "w"), stderr=subprocess.STDOUT) == 0

	@property
	def ports(self):
		ports = {}
		for acm in filter(lambda i:i.startswith("ttyACM"), os.listdir("/sys/class/tty/")):
			f = os.path.join("/sys/class/tty/", acm, "device/interface")
			if os.path.exists(f):
				fstr = open(f).read().strip()
				if fstr == "Ericsson F3507g Mobile Broadband Minicard Data Modem":
					ports['wwan'] = os.path.join('/dev', acm)
				elif fstr == "Ericsson F3507g Mobile Broadband Minicard GPS Port":
					ports['gps'] = os.path.join('/dev', acm)
		return ports

	@property
	def ip(self):
		ip_addr = None
		proc = subprocess.Popen(
			["ip -%d -o addr | awk '!/^[0-9]*: ?lo|link\/ether/ {gsub(\"/\", \" \"); print $2\" \"$4}'" % config["ipver"]],
			shell=True,
			stdout=subprocess.PIPE
		)
		for line in iter(proc.stdout.readline, ''):
			line = line.strip()
			intf, ipaddr = line.split()
			if config["ipver"] == 6 and ipaddr.startswith("fe80"):
				continue
			if intf == config["wwan_interface"]:
				ip_addr = ipaddr
		proc.wait()
		return ip_addr
