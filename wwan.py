#!/usr/bin/python
# -*- coding: utf-8 -*-

# Author: Barry John Williams, Dominik Heidler
# Creative Commons Attribute-Share Alike 2.5 UK:Scotland Licence

import serial
import string
import sys
import os
import shlex
import pygtk
pygtk.require('2.0')
import gtk
import pynotify
import time
import threading
import signal
import subprocess

class DictObj:
	def __init__(self, d):
		self.d = d
	def __getattr__(self, a):
		return self.d.get(a, None)

radio = DictObj({
	'ERROR': 0,
	'PREFER': 1,
	'OFF': 4,
	'GPRS': 5,
	'UMTS': 6
	})

class Monitor:

	ERINFO_GPRS = '0,1,0'
	ERINFO_EDGE = '0,2,0'
	ERINFO_UMTS = '0,0,1'
	ERINFO_HSPA = '0,0,2'

	GPRS = 'G'
	EDGE = 'E'
	UMTS = '3G'
	HSPA = 'H'
	NONE = 'NONE'

	def __init__(self):
		self.setSerial(serial.Serial())
		self.reset()

	def reset(self):
		print 'Values reset'
		self.cur_network = ''
		self.cur_type = ''
		self.cur_signal = 0

	def setSerial(self, ser):
		self.ser = ser

	def getSerial(self):
		return self.ser

	def call(self, ser, command):
		try:
			ser.write(command + '\r\n')
			# strip 1st element (holds our command or '\r\n' on E0)
			out = ser.readlines()[1:]
			response = [r.replace('\r\n', '') for r in out if not r.startswith(('^', '_'))]
			print
			print "reqw: %s" % str(command)
			print "cals: %s" % str(response)
			print
			return response
		except (OSError, serial.SerialException) as e:
			print "Error performing serial call"
			try:
				print e.args[-1]
			except:
				pass
			return []

	# This function returns meaningful results only when in GPRS mode - it therefore isn't used but kept for reference
	def get_csq_signal(self):
		signal_res = call(self.ser, 'AT+CSQ')
		if len(signal_res) > 2:
			csq = signal_res[1].replace('+CSQ: ', '')
			csq_val = int(csq[:string.find(csq, ',')])
			strength = 100 * csq_val / 31
			# following calculation taken from http://www.gprsmodems.co.uk/acatalog/Technical_Topics.html
			rssi = -113 + csq_val * 2
			return [strength, rssi]
		else:
			return [0, 0]

	def get_type(self):
		return self.cur_type

	def get_network(self):
		return self.cur_network

	def get_signal(self):
		return self.cur_signal

	# Returns True if the state of the access type has changed since the last call
	def update_type(self):
		"""
		AT*ERINFO?
		*ERINFO: 0,2,0
		"""
		response = self.call(self.ser, 'AT*ERINFO?')
		type = self.NONE
		if len(response) >= 2:
			erinfo = response[0].replace('*ERINFO: ', '')
			if erinfo == self.ERINFO_GPRS:
				type = self.GPRS
			elif erinfo == self.ERINFO_EDGE:
				type = self.EDGE
			elif erinfo == self.ERINFO_UMTS:
				type = self.UMTS
			elif erinfo == self.ERINFO_HSPA:
				type = self.HSPA
			print "type: %s" % type
			if type != self.cur_type:
				self.cur_type = type
				return True
		return False

	# Returns True if the signal level has changed since the last call
	def update_signal(self):
		"""
		AT+CIND?
		+CIND: 4,2,0,0,1,0,0,0,0,0,0,0
		         ^ signal
		"""
		response = self.call(self.ser, 'AT+CIND?')
		signal = 0
		if len(response) >= 2:
			cind = response[0].replace('+CIND: ', '').split(',')
			if len(cind) > 2:
				signal = int(cind[1])
				print "signal: %s" % str(signal)
			if signal != self.cur_signal:
				self.cur_signal = signal
				return True
		return False

	# Returns True if the network has changed since the last call
	def update_network(self):
		"""
		AT+COPS?
		+COPS: 0,0,"Telekom.de",2
		"""
		response = self.call(self.ser, 'AT+COPS?')
		network = 'Searching'
		if len(response) >= 2:
			if (response[0])[:6] == '+COPS:':
				index = string.find(response[0], '"')
				index2 = string.find((response[0])[index + 1:], '"') + index
				network_string = (response[0])[index + 1:index2 + 1]
				if index2 > index:
					print "network: %s" % str(network_string)
					network = network_string
					if network != self.cur_network:
						self.cur_network = network
						return True
		return False

	def close(self):
		if self.ser.isOpen():
			self.ser.close()


class StatusIcon:

	NONE_ICON = 'notification-disabled.svg'

	UMTS_ICON = [
		'notification-gsm-disconnected.svg',
		'notification-gsm-3g-none.svg',
		'notification-gsm-3g-low.svg',
		'notification-gsm-3g-medium.svg',
		'notification-gsm-3g-high.svg',
		'notification-gsm-3g-full.svg',
		]

	HSPA_ICON = [
		'notification-gsm-disconnected.svg',
		'notification-gsm-h-none.svg',
		'notification-gsm-h-low.svg',
		'notification-gsm-h-medium.svg',
		'notification-gsm-h-high.svg',
		'notification-gsm-h-full.svg',
		]

	GPRS_ICON = [
		'notification-gsm-disconnected.svg',
		'notification-gsm-none.svg',
		'notification-gsm-low.svg',
		'notification-gsm-medium.svg',
		'notification-gsm-high.svg',
		'notification-gsm-full.svg',
		]

	EDGE_ICON = [
		'notification-gsm-disconnected.svg',
		'notification-gsm-none.svg',
		'notification-gsm-edge-low.svg',
		'notification-gsm-edge-medium.svg',
		'notification-gsm-edge-high.svg',
		'notification-gsm-edge-full.svg',
		]

	def __init__(self, controller):
		self.controller = controller
		file = os.path.join('icons', StatusIcon.NONE_ICON)
		if not os.access(file, os.F_OK):
			print "Can't access icon %s" % StatusIcon.NONE_ICON
		self.status_icon = gtk.status_icon_new_from_file(file)
		self.status_icon.set_visible(True)
		# prevent running callbacks, when changing button values from program
		self.allowcallbacks = True

		# Build Context Menu
		menu = gtk.Menu()

		self.radioRadioMenu = dict()

		normalRadioMenuItem = gtk.RadioMenuItem(None, 'Normal (Prefer 3G)')
		normalRadioMenuItem.connect('toggled', self.normalRadio_menu_cb)
		self.radioRadioMenu[radio.PREFER] = normalRadioMenuItem
		menu.append(normalRadioMenuItem)

		umtsRadioMenuItem = gtk.RadioMenuItem(normalRadioMenuItem, 'UMTS/HSPA (3G Only)')
		self.radioRadioMenu[radio.UMTS] = umtsRadioMenuItem
		umtsRadioMenuItem.connect('toggled', self.umtsRadio_menu_cb)
		menu.append(umtsRadioMenuItem)

		gprsRadioMenuItem = gtk.RadioMenuItem(umtsRadioMenuItem, 'GPRS Only')
		self.radioRadioMenu[radio.GPRS] = gprsRadioMenuItem
		gprsRadioMenuItem.connect('toggled', self.gprsRadio_menu_cb)
		menu.append(gprsRadioMenuItem)

		menu.append(gtk.SeparatorMenuItem())

		self.enabledMenuItem = gtk.CheckMenuItem('Enabled')
		self.enabledMenuItem.connect('toggled', self.enable_menu_cb)
		menu.append(self.enabledMenuItem)

		menu.append(gtk.SeparatorMenuItem())

		aboutMenuItem = gtk.MenuItem("About")
		aboutMenuItem.connect('activate', self.show_about_dialog_cb)
		menu.append(aboutMenuItem)

#		exitMenuItem = gtk.MenuItem('Exit')
#		exitMenuItem.connect('activate', self.close_menu_cb)
#		menu.append(exitMenuItem)

#		self.status_icon.connect('activate', self.activate_cb)
		self.status_icon.connect('popup-menu', self.popup_menu_cb, menu)

	def popup_menu_cb(self, statusicon, button, time, menu=None):
		if button == 3:
			if menu:
				menu.show_all()
				menu.popup(None, None, gtk.status_icon_position_menu, button, time, statusicon)
		pass

	def normalRadio_menu_cb(self, widget, data=None):
		if self.allowcallbacks:
			print "UI-CALLBACK: PREFER"
			self.controller.setRadio(radio.PREFER)

	def umtsRadio_menu_cb(self, widget, data=None):
		if self.allowcallbacks:
			print "UI-CALLBACK: UMTS"
			self.controller.setRadio(radio.UMTS)

	def gprsRadio_menu_cb(self, widget, data=None):
		if self.allowcallbacks:
			print "UI-CALLBACK: GPRS"
			self.controller.setRadio(radio.GPRS)

	def enable_menu_cb(self, widget, data=None):
		if self.allowcallbacks:
			print "UI-CALLBACK: enable button %s" % str(widget.get_active())
			state = radio.PREFER if widget.get_active() else radio.OFF
			self.controller.setRadio(state)

	def close_menu_cb(self, widget, data=None):
		# Hide the icon first to give instant semantic feedback
		self.status_icon.set_visible(False)
		# The controller should close this status icon properly once its thread has completed
		self.controller.close()

	def show_about_dialog_cb(self, widget):
		about_dialog = gtk.AboutDialog()

		about_dialog.set_destroy_with_parent(True)
		about_dialog.set_name('wwan control')
		about_dialog.set_version('0.1')
		about_dialog.set_authors(['Barry John Williams', 'Dominik Heidler'])
		about_dialog.set_license("Creative Commons Attribute-Share Alike 2.5 UK:Scotland Licence")

		about_dialog.run()
		about_dialog.destroy()

#	def activate_cb(self, widget, data=None):
#		bandwidth = self.get_bandwidth()
#		message = 'Bandwidth: %s' % bandwidth
#		print message
#		n = pynotify.Notification('Mobile Broadband', message)
#		if not n.show():
#			print 'Failed to send notification'

	def get_icon_file(self, type, signal):
		iconname = StatusIcon.NONE_ICON
		if type == Monitor.GPRS:
			iconname = self.GPRS_ICON[signal]
		elif type == Monitor.EDGE:
			iconname = self.EDGE_ICON[signal]
		elif type == Monitor.UMTS:
			iconname = self.UMTS_ICON[signal]
		elif type == Monitor.HSPA:
			iconname = self.HSPA_ICON[signal]
		return os.path.join('icons', iconname)

	def update(self, radiostate, network, type, signal):
		filename = self.get_icon_file(type, signal)
		if not os.access(filename, os.F_OK):
			print "Can't access icon %s" % filename
		if not network:
			message = 'No Network'
		else:
			message = '%s (%s)' % (network, type)
		gtk.gdk.threads_enter()
		self.status_icon.set_from_file(filename)
		if radiostate == radio.ERROR or radiostate == radio.OFF:
			#self.status_icon.set_has_tooltip(False)
			self.status_icon.set_tooltip('Disabled')
			[item.set_sensitive(False) for item in self.radioRadioMenu.values()]
			self.allowcallbacks = False
			self.enabledMenuItem.set_active(False)
			self.allowcallbacks = True
		else:
			self.status_icon.set_has_tooltip(True)
			self.status_icon.set_tooltip(message)
			[item.set_sensitive(True) for item in self.radioRadioMenu.values()]
			self.allowcallbacks = False
			self.enabledMenuItem.set_active(True)
			self.radioRadioMenu[radiostate].set_active(True)
			self.allowcallbacks = True
		gtk.gdk.threads_leave()

	def notify_status(self,	network, type, signal):
		if type == Monitor.NONE:
			message = 'Searching'
		else:
			message = network + ' (' + type + ')'
		n = pynotify.Notification('Mobile Broadband', message)  # , self.get_icon_file(type,signal))
		if not n.show():
			print 'Failed to send notification'

	def main(self):
		gtk.main()

	def stop(self):
		gtk.main_quit()


class Controller(threading.Thread):

	def __init__(self, serialNode):
		print 'Controller on %s' % serialNode
		self.monitor = Monitor()
		self.ui = StatusIcon(self)
		self.running = True
		self.event = threading.Event()
		self.updateRadioState = False
		self.setRadioState = radio.OFF
		self.serialNode = serialNode
		self.lasttype = radio.OFF
		threading.Thread.__init__(self)

	def close(self):
		self.running = False
		self.event.set()

	def getRadioState(self):
		ser = self.monitor.getSerial()
		if ser.isOpen():
			#if not ser.port:
			#	# because of rfkill there may be no serial device
			#	return radio.OFF
			ser = self.monitor.getSerial()
			response = self.monitor.call(ser, "AT+CFUN?")
			if len(response) >= 2:
				output = response[0].replace('+CFUN: ','')
				if (output == '1'):
					return radio.PREFER
				elif (output == '4'):
					return radio.OFF
				elif (output == '5'):
					return radio.GPRS
				elif (output == '6'):
					return radio.UMTS
			else:
				return radio.ERROR
		return radio.ERROR

	def setRadio(self, state):
		print 'Requsted state %s' % state
		self.updateRadioState = True
		self.setRadioState = state
		self.event.set()

	def _setRadio(self, type):
		if self.lasttype != type:
			if self.lasttype == radio.OFF:
				subprocess.call(['/etc/rc.d/wwan', 'start'])
			elif type == radio.OFF:
				subprocess.call(['/etc/rc.d/wwan', 'stop'])
				self.monitor.reset()
				self.monitor.setSerial(serial.Serial())
			else:
				ser = self.monitor.getSerial()
				self.monitor.call(ser, "AT+CFUN=%s" % str(type))
			self.lasttype = type

	def run(self):
		print 'Starting monitoring loop'
		while self.running:
			try:
				# Reopen Monitor
				try:
					self.monitor.setSerial(serial.Serial(self.serialNode, 19200, timeout=0.25))
				except serial.serialutil.SerialException:
					print 'Failure Opening Serial Port'
					self.monitor.reset()
					self.lasttype = radio.OFF
					self.monitor.setSerial(serial.Serial())

				# If radio state change request has been made
				if self.updateRadioState:
					print 'Changing Radio State to %s' % self.setRadioState
					self._setRadio(self.setRadioState)
					self.updateRadioState = False

				# Fetch new data using serial
				if self.monitor.getSerial().isOpen():
					self.monitor.update_signal()
					if self.monitor.update_network() | self.monitor.update_type():
						try:
							self.ui.notify_status(self.monitor.get_network(), self.monitor.get_type(), self.monitor.get_signal())
						except:
							print "ERROR: No notification-daemon running"
				else:
					self.monitor.reset()

			except OSError as e:
				try:
					print 'Error: %s' % e.args[-1]
				except:
					print 'Error: OSError'
				self.monitor.reset()

			# Update UI
			radioState = self.getRadioState()
			print "set last: %s" % str(radioState)
			self.lasttype = radioState
			self.ui.update(radioState, self.monitor.get_network(), self.monitor.get_type(), self.monitor.get_signal())

			# Close Monitor
			self.monitor.close()

			# Wait 4 Seconds
			self.event.clear()
			self.event.wait(4)

		print 'Exiting'
		self.monitor.close()
		self.ui.stop()


if __name__ == '__main__':
	if not pynotify.init('Basics'):
		sys.exit(1)

	# Set the working folder to that set in command line
	serialNode = None
	if len(sys.argv) > 0:
		serialNode = sys.argv[1]

	if len(sys.argv) > 1:
		dir = sys.argv[2]
		if os.access(dir, os.F_OK):
			print 'Working Dir: %s' % dir
			os.chdir(dir)
		else:
			print 'Dir %s does not exist' % dir
			sys.exit(1)

	if serialNode != None:
		# controller = Controller('/dev/ttyACM1')
		controller = Controller(serialNode)

		def signal_handler(sig, frame):
			print 'Caught Signal ' + str(sig)
			controller.close()

		signal.signal(signal.SIGTERM, signal_handler)
		signal.signal(signal.SIGINT, signal_handler)

		gtk.gdk.threads_init()

		# Start the controller thread
		controller.start()

		# Start the UI
		controller.ui.main()
	else:
		print 'Missing serial device'
		sys.exit(1)
