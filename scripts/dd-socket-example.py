#!/usr/bin/env python3
from socket import socket, AF_INET, SOCK_STREAM
from subprocess import Popen, PIPE
try:
	from delta_debugging.DD import DD
except ImportError as e:
	print("Unable to import delta debugging library.  Please ensure it is "
		"installed.  https://github.com/grimm-co/delta-debugging")
	from sys import exit
	exit(-1)


HOST="192.168.192.169"
PORT=5900
class MyDD(DD):
	def __init__(self):
		DD.__init__(self)
		self.debug_dd = 1
		# Caching results in a memory explosion for long runs
		self.cache_outcomes = 0
        
	def _test(self, deltas):
		# Build input
		data = []
		for (index, byte) in deltas:
			data.append(byte)

		# Write input to `input.c'
		#out = open('input.tmp', 'wb')
		#out.write(bytes(data))
		#out.close()

		#print(self.coerce(deltas))

		s = socket(AF_INET, SOCK_STREAM)
		try:
			s.connect((HOST, PORT))
			if data:
				s.sendall(bytes("".join(data), "UTF-8"))

			if self.target_crashed():
				return self.FAIL
			return self.PASS
		except Exception as e:
			print("EXCEPTION: %s" % str(e))
		return self.UNRESOLVED

	def coerce(self, deltas):
		# Pretty-print the configuration
		data = []
		for (index, byte) in deltas:
			data.append(byte)
		return data

	def target_crashed(self):
		s = socket(AF_INET, SOCK_STREAM)
		try:
			s.connect((HOST, PORT))
			s.close()
			return False
		except Exception as e:
			print("%s - %s" % (type(e), str(e)))
			return True

if __name__ == '__main__':
	mydd = MyDD()
	# Load deltas from input file
	deltas = []
	index = 1
	for character in open('crash_delta').read():
		deltas.append((index, character))
		index = index + 1

    
	print("Simplifying failure-inducing input...")
	c = mydd.ddmin(deltas)              # Invoke DDMIN
	print("The 1-minimal failure-inducing input is %s" % mydd.coerce(c))
	print("Removing any element will make the failure go away.")

	# print("Isolating the failure-inducing difference...")
	# (c, c1, c2) = mydd.dd(deltas)	# Invoke DD
	# print("The 1-minimal failure-inducing difference is", c)
	# print(mydd.coerce(c1), "passes,", mydd.coerce(c2), "fails")
