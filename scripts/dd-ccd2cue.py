#!/usr/bin/env python3
from argparse import ArgumentParser
from logging import basicConfig, DEBUG, INFO, WARNING, debug, info, error
from os import unlink
from subprocess import TimeoutExpired
from sys import stdin
from tempfile import mkstemp
from threading import Thread

try:
	from delta_debugging.DD import DD
	from delta_debugging.gdb import Gdb
except ImportError as e:
	print("Unable to import delta debugging library.  Please ensure it is "
		"installed.  https://github.com/grimm-co/delta-debugging")
	from sys import exit
	exit(-1)

class GdbDD(DD):
	def __init__(self, executable, target_args, loglevel=INFO):
		DD.__init__(self)
		self.executable = executable
		self.target_args = target_args
		if loglevel >= INFO:
			self.debug_dd = 0
			self.verbose = 0
		else:
			self.debug_dd = 1
			self.verbose = 1
		# Caching results in a memory explosion for long runs
		self.cache_outcomes = 0

	def wait_for_gdb(self, gdb):
		"""
		This will run GDB in a separate thread.
		"""
		try:
			info("Starting watchdog thread")
			if gdb.p:  # our process is gone, hooray
				info("Checking to see if gdb is finished")
				gdb.p.wait(timeout=5)
				if gdb.p and gdb.p.returncode is None:  # If gdb isn't finished by now...
					gdb.p.kill()          # kill it
			else:
				info("GDB has finished")
		except TimeoutExpired:
			pass

	def _test(self, deltas):
		# Build input file
		input_filename = mkstemp(prefix="ccd2cue-crash-", suffix=".ccd")[1]
		with open(input_filename, "wb") as f:
			for (index, byte) in deltas:
				f.write(bytes([byte]))

		g = Gdb(self.executable)

		# Append the input filename to the target args & run
		args = []
		for entry in self.target_args:
			args.append(entry)
		args.append(input_filename)
		debug("Running: {} {}".format(self.executable, " ".join(args)))
		t = Thread(target=self.wait_for_gdb, kwargs={"gdb": g})
		t.start()  # Start waiting for gdb
		response = g.run(args=args, read_to_prompt=True)
		debug("gdb response = {}".format(response))

		# Clean up our temporary files
		unlink(input_filename)

		# Check for cases where we didn't crash
		if ("exited normally" in response or "exited with code" in response):
			g.quit()
			t.join()
			return self.PASS

		if "SIGABRT" in response:
			g.quit()
			t.join()
			return self.FAIL

		# Shouldn't ever happen
		error("Unhandled exception occurred {}".format(response))
		g.quit()
		t.join()
		return self.UNRESOLVED

if __name__ == '__main__':
	parser = ArgumentParser(description=("Delta debugging test script to determine the minimum input "
					"which will still crash ccd2cue."))
	parser.add_argument('executable', help=('The path to ccd2cue'))
	parser.add_argument('--input-file', default=None,
				help=('The filename of the crashing input (Default: stdin)'))
	parser.add_argument('--target-args', default="", help="The arguments to pass to the ccd2cue "
        "(excluding the input file)")
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
		debug("Using input file: {}".format(args.input_file))
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
		mydd = GdbDD(args.executable, args.target_args.split(" "), loglevel)
	else:
		mydd = GdbDD(args.executable, [], loglevel)
	info("Simplifying failure-inducing input...")
	c = mydd.ddmin(deltas)              # Invoke DDMIN
	with open("crash-minimal.ccd", "wb") as f:
		for (index, byte) in c:
			f.write(bytes([byte]))
	info("The 1-minimal failure-inducing input has been saved to crash-minimal.ccd")
	info("Removing any element will make the failure go away.")

