#!/usr/bin/python

# Author: Barry John Williams, Dominik Heidler
# Creative Commons Attribute-Share Alike 2.5 UK:Scotland Licence

import serial
import sys
import subprocess

STATE = {
	'1': 'PREFER',
	'4': 'OFF',
	'5': 'GPRS',
	'6': 'UMTS'
}

ERROR = 0
PREFER = 1
OFF = 4
GPRS = 5
UMTS = 6

laststate = OFF

#def on(ser, type):
#	ser.write('ATZ E0 V1 X4 &C1\r\n')
#	ser.readline()
#	ser.flushOutput()
#	ser.flushInput()
#	ser.write('AT+CFUN='+str(type)+'\r\n')
#	response = [r.replace('\r\n', '') for r in ser.readlines()
#		if not r.startswith(('^', '_')) and r.replace('\r\n','')]
#
#def off(ser):
#	ser.write('AT+CFUN=4\r\n')
#	response = [r.replace('\r\n', '') for r in ser.readlines()
#		if not r.startswith(('^', '_')) and r.replace('\r\n','')]

def on():
	subprocess.call(['/etc/rc.d/wwan', 'start'])

def off():
	subprocess.call(['/etc/rc.d/wwan', 'stop'])

def set_status(ser, type):
	global laststate
	if laststate != type:
		if laststate == OFF:
			on()
		elif type == OFF:
			off()
		if type != OFF:
			ser.flushOutput()
			ser.flushInput()
			ser.write('AT+CFUN='+str(type)+'\r\n')
			response = [r.replace('\r\n', '') for r in ser.readlines() if not r.startswith(('^', '_')) and r.replace('\r\n','')]
		laststate = type

def status(ser):
	if laststate == OFF:
		# because of rfkill there may be no serial device
		return OFF
	ser.write('AT+CFUN?\r\n')
	response = [r.replace('\r\n', '') for r in ser.readlines() if not r.startswith(('^', '_')) and r.replace('\r\n','')]
	if len(response) > 2:
		output = response[1].replace('+CFUN: ','')
		if (output == '1'):
			return PREFER
		elif (output == '4'):
			return OFF
		elif (output == '5'):
			return GPRS
		elif (output == '6'):
			return UMTS
	else:
		return ERROR

if __name__ == '__main__':
	ser = serial.Serial('/dev/ttyACM0', 19200, timeout=0.2)

	for arg in sys.argv:
		if arg in ("ON","on"):
			on(ser,UMTS)
		elif arg in ("OFF","off"):
			off(ser)
		
	print status(ser)
	ser.close()
