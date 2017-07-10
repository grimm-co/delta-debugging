#!/usr/bin/env python3
from argparse import ArgumentParser
from logging import basicConfig, DEBUG, INFO, WARNING, debug, info, error
from os import unlink
from subprocess import TimeoutExpired
from sys import stdin
from tempfile import mkstemp
from threading import Thread
from time import sleep

try:
	from delta_debugging.DD import DD
except ImportError as e:
	print("Unable to import delta debugging library.  Please ensure it is "
		"installed.  https://www.st.cs.uni-saarland.de/askigor/downloads/")
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
			if gdb.p:  # our process is gone, horray
				info("Checking to see if gdb is finished")
				gdb.p.wait(timeout=5)
				if gdb.p and gdb.p.returncode is None:  # If gdb isn't finished by now...
					gdb.p.kill()          # kill it
			else:
				info("GDB has finished")
		except TimeoutExpired:
			pass

	def _test(self, deltas):
		# Build input
		input_filename = mkstemp(prefix="sqlite3-crash-", suffix=".sql")[1]
		db_filename = mkstemp(prefix="sqlite3-", suffix=".db")[1]
		with open(input_filename, "wb") as f:
			for (index, byte) in deltas:
				f.write(bytes([byte]))

		g = Gdb(self.executable)	
		debug("Running %s" % self.executable)
		g._send_command("set disassembly-flavor intel")

		# Append the stream redirection from our tempfile to the target args & run
		args = []
		for entry in self.target_args:
			args.append(entry)
		args.extend([db_filename, "<", input_filename])
		debug("target_args: %s" % args)
		t = Thread(target=self.wait_for_gdb, kwargs={"gdb": g})
		t.start()  # Start waiting for gdb
		debug("Running gdb")
		response = g.run(args=args, read_to_prompt=True)
		debug("Gdb exited or hit exception")
		debug("response = %s" % response)

		# Clean up our remporary files
		unlink(input_filename)
		unlink(db_filename)

		# Check for cases where we didn't crash
		if "exited normally" in response:   # We're done
			g.quit()
			t.join()
			return self.PASS
		if "exited with code" in response:  # We're done
			g.quit()
			t.join()
			return self.PASS

		try:
			g._determine_pc()
			addr = g.info_registers([g.pc])[g.pc]
			#if addr == 0:
			#	g.quit()
			#	return self.PASS  # We don't want the pointer to be at the NULL page
			info("Faulted at 0x%x" % addr)
		except ValueError as e:
			error("Unable to determine faulting addr %s %s" % (str(e), response))

		if "SIGABRT" in response:
			g.quit()
			t.join()
			return self.PASS  # This isn't the crash we are looking for
			#return self.FAIL  # I changed my mind, we do care about this
		elif "SIGSEGV" in response and "a99410" in response:
			#target_rip = "0x0000000000a99410"
			#response = g._send_command("x/gx $rip")
			g.quit()
			t.join()
			return self.FAIL  # This is the crash we care about
			#if target_rip in response:
			#	return self.FAIL  # This is the crash we care about
			#return self.PASS  # This isn't the crash we are looking for
		error("WTF just happened? %s" % response)
		g.quit()
		t.join()
		return self.UNRESOLVED

	def stringify(self, deltas):
		data = []
		for (index, byte) in deltas:
			data.append(byte)
		return "".join(data)

	def target_crashed(self):
		s = socket(AF_INET, SOCK_STREAM)
		try:
			s.connect((HOST, PORT))
			s.close()
			return False
		except Exception as e:
			error("%s - %s" % (type(e), str(e)))
			return True

if __name__ == '__main__':
	parser = ArgumentParser(description=("Sample program to find the minimum input which "
					"will hit the specified breakpoint.  This program "
					"assumes that an empty input will not hit the breakpoint."))
	parser.add_argument('executable', help=('The name of the executable to debug'))
	parser.add_argument('--input-file', default=None,
				help=('The filename of the crashing input (Default: stdin)'))
	parser.add_argument('--target-args', default="", help="The arguments to pass to the target binary")
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
		mydd = GdbDD(args.executable, args.target_args.split(" "), loglevel)
	else:
		mydd = GdbDD(args.executable, [], loglevel)
	info("Simplifying failure-inducing input...")
	c = mydd.ddmin(deltas)              # Invoke DDMIN
	with open("crash-minimal.sql", "wb") as f:
		for (index, byte) in c:
			f.write(bytes([byte]))
	info("The 1-minimal failure-inducing input has been saved to crash-minimal.sql")
	info("Removing any element will make the failure go away.")

	# debug("Isolating the failure-inducing difference...")
	# (c, c1, c2) = mydd.dd(deltas)	# Invoke DD
	# info("The 1-minimal failure-inducing difference is", c)
	# info(mydd.stringify(c1), "passes,", mydd.stringify(c2), "fails")
