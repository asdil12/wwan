#!/usr/bin/python2

from wwan import control
from time import sleep
import sys

c = control.WWANControl()

try:
	c.enable()
	while True:
		sys.stdout.write("\r[%i/5 %s] %s" % (
			c.modem.signal_strength,
			c.modem.aquired_radio_technology,
			c.modem.network_name
		))
		sys.stdout.flush()
		sleep(1)
except KeyboardInterrupt:
	print ""
	c.disable()
