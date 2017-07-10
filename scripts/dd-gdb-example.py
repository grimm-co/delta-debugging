#!/usr/bin/env python3
from argparse import ArgumentParser
from logging import basicConfig, DEBUG, INFO, debug, info, error
from sys import stdin

try:
	from delta_debugging.DD import DD
except ImportError as e:
	print("Unable to import delta debugging library.  Please ensure it is "
		"installed.  See https://github.com/grimm-co/delta-debugging "
		"for details")
	from sys import exit
	exit(-1)

class GdbDD(DD):
	def __init__(self, executable, breakpoint, verbose=False):
		DD.__init__(self)
		self.executable = executable
		self.breakpoint = breakpoint
		self.debug_dd = (0, 1)[verbose]
		self.verbose = (0, 1)[verbose]
		# Caching results in a memory explosion for long runs
		self.cache_outcomes = 0
        
	def _test(self, deltas):
		# Build input
		data = []
		for (index, byte) in deltas:
			data.append((index, byte))

		g = Gdb(self.executable)	
		breakpoint_number, addr = g.set_breakpoint(self.breakpoint)
		debug("Breakpoint %d set at %s" % (breakpoint_number, addr))

		debug("Running %s" % self.executable)
		g.run(read_to_prompt=False)

		debug("Sending input to GDB")
		g.send_input(self.stringify(data), read_to_prompt=False)
		response = g.send_EOF()

		if "breakpoint" in response.lower():
			debug("Breakpoint hit")
			return self.FAIL  # simulated crash
		elif "exited" in response.lower():
			debug("Breakpoint not hit")
			return self.PASS
		debug("WTF just happened?")
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
	parser.add_argument('breakpoint', help="The location which, if hit, indicates the path we're interested in")
	parser.add_argument('--input_file', default=None,
				help=('The filename of the interesting/crashing input (Default: stdin)'))
	#parser.add_argument('good_input_file', help=('The filename of the non-interesting input'))
	#parser.add_argument('crash_input_file', help=('The filename of the interesting/crashing input'))
	parser.add_argument('-v', action='store_true', help=('Verbose output (for debugging issues)'))

	args = parser.parse_args()
	basicConfig(format="[%(levelname)s] %(asctime)s - %(message)s", level=(INFO, DEBUG)[args.v])
	if args.input_file:
		infile = open(args.input_file, "rb")
	else:
		infile = stdin

	# Load deltas from input file
	deltas = []
	index = 1
	for character in infile.read():
		deltas.append((index, character))
		index = index + 1

	mydd = GdbDD(args.executable, args.breakpoint, args.v)
	info("Simplifying failure-inducing input...")
	c = mydd.ddmin(deltas)              # Invoke DDMIN
	info("The 1-minimal failure-inducing input is %s" % mydd.stringify(c))
	info("Removing any element will make the failure go away.")

	# debug("Isolating the failure-inducing difference...")
	# (c, c1, c2) = mydd.dd(deltas)	# Invoke DD
	# info("The 1-minimal failure-inducing difference is", c)
	# info(mydd.stringify(c1), "passes,", mydd.stringify(c2), "fails")
