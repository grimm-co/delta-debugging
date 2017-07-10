#!/usr/bin/python3
from argparse import ArgumentParser
from logging import basicConfig, DEBUG, INFO, WARNING, debug, info, error
from os import close, unlink
from subprocess import TimeoutExpired, Popen, PIPE, STDOUT
from sys import stdin
from tempfile import mkstemp
from threading import Thread
from time import sleep

try:
	from delta_debugging.DD import DD
except ImportError as e:
	print("Unable to import delta debugging library.  Please ensure it is "
		"installed.  https://github.com/grimm-co/delta-debugging ")
	from sys import exit
	exit(-1)

class MyDD(DD):
	def __init__(self, executable, target_args, streaming=False, loglevel=INFO):
		DD.__init__(self)
		self.executable = executable
		self.target_args = target_args
		self.streaming = streaming
		if loglevel >= INFO:
			self.debug_dd = 0
			self.verbose = 0
		else:
			self.debug_dd = 1
			self.verbose = 1
		# Caching results in a memory explosion for long runs
		self.cache_outcomes = 0
        
	def _test(self, deltas):
		# Build input
		_, input_filename = mkstemp(prefix="crash-")
		close(_)  # We just wanted the unique filename, not an open file descriptor...

		_args = [self.executable]
		if self.target_args:
			_args.extend([x if x != "@@" else input_filename for x in self.target_args])

		with open(input_filename, "wb") as f:
			for (index, byte) in deltas:
				f.write(bytes([byte]))
		p = Popen(_args, stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True)
		if self.streaming:
			with open(input_filename, "rb") as infile:
				p.stdin.write(infile.read())
			p.stdin.close()
		p.wait()

		# Clean up our remporary files
		unlink(input_filename)

		debug("Return code: %d" % p.returncode)
		if p.returncode == 0:
			return self.PASS
		# This means the syntax was wrong, but it doesn't mean it crashed!
		# 255 = Operation not permitted
		#if p.returncode in [255, 69, 73]:
		#	return self.PASS
		info("Return code: %d" % p.returncode)
		return self.FAIL

	def stringify(self, deltas):
		data = []
		for (index, byte) in deltas:
			data.append(byte)
		return "".join(data)

if __name__ == '__main__':
	parser = ArgumentParser(description=("Sample program to find the minimum input which "
					"will hit the specified breakpoint.  This program "
					"assumes that an empty input will not hit the breakpoint."))
	parser.add_argument('executable', help=('The name of the executable to debug'))
	parser.add_argument('--input-file', default=None,
				help=('The filename of the initial (crashing) test case (Default: stdin)'))
	parser.add_argument('--output-file', default="crash-minimal",
				help=('The output file to create (Default: crash-minimal)'))
	parser.add_argument('--target-args', default="", help="The arguments to pass to the target binary (use @@ for input file)")
	parser.add_argument('-s', action='store_true', help=('Push file through stdin to target application'))
	parser.add_argument('-q', action='store_true', help=('Quite mode (overrides -v if both are given)'))
	parser.add_argument('-v', action='store_true', help=('Verbose output (for debugging issues)'))

	args = parser.parse_args()
	if args.q:
		loglevel = WARNING
	elif args.v:
		loglevel = DEBUG
	else:
		loglevel = INFO

	basicConfig(format="[%(levelname)s] %(asctime)s - %(message)s", level=loglevel)
	if args.input_file:
		debug("Using input file: %s" % args.input_file)
		infile = open(args.input_file, "rb")
	else:
		infile = stdin

	# Load deltas from input file
	deltas = []
	index = 1
	for character in infile.read():
		deltas.append((index, character))
		index = index + 1

	if args.target_args:
		mydd = MyDD(args.executable, args.target_args.split(" "), args.s, loglevel)
	else:
		mydd = MyDD(args.executable, [], args.s, loglevel)
	info("Simplifying failure-inducing input...")
	c = mydd.ddmin(deltas)              # Invoke DDMIN
	with open(args.output_file, "wb") as f:
		for (index, byte) in c:
			f.write(bytes([byte]))
	info("The 1-minimal failure-inducing input has been saved to %s" % args.output_file)
	info("Removing any element will make the failure go away.")

	debug("Isolating the failure-inducing difference...")
	(c, c1, c2) = mydd.dd(deltas)	# Invoke DD
	info("The 1-minimal failure-inducing difference is %s", c)
	info(mydd.stringify(c1), "passes,", mydd.stringify(c2), "fails")
