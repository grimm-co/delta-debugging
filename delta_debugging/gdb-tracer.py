#!/usr/bin/env python3
from argparse import ArgumentParser
from gdb import Gdb, GdbException
from logging import debug, info, error, basicConfig, INFO, DEBUG
from sys import stdout

class GdbTracer(Gdb):
	"""
	This will trace every branch within the target binary, but not dig
	into the libraries.  Tracing into libraries would be very resource
	intensive.  If you are willing to pay that cost, simply create your
	own subclass and make it happen!
	"""
	def get_target_info(self):
		"""
		This will get target info such as the entry point as well as
		the memory ranges for the base executable.  These ranges are
		later used to determine which function calls to step into
		versus which ones to step over.

		:returns: The entry point
		:rtype: int
		"""
		self._determine_executable_range()
		return self._determine_entry_point()

	def _determine_entry_point(self):
		"""
		This will determine the entry point for the program and
		return that value as an integer.

		:returns: The entry point
		:rtype: int
		"""
		response = self._send_command("info target")
		for line in response.splitlines():
			line = line.strip()
			if line.startswith("Entry point: "):
				return int(line[13:], 16)

	def _determine_executable_range(self):
		"""
		This will determine where the target program has been loaded
		in memory.  Obviously this requires the program to have been
		started using _start_program().  The memory range for the 
		target is saved in a list called self.target_ranges.

		:returns: None
		:rtype: None
		"""
		self.target_ranges = []
		response = self._send_command("info target")
		for line in response.splitlines():
			line = line.strip()
			if not line.startswith("0x"):
				continue
			if " in " in line:  # library
				continue
			parts = line.split(" ")
			self.target_ranges.append( (int(parts[0], 16), int(parts[2], 16)) )
		self._consolidate_target_ranges()

	def _consolidate_target_ranges(self):
		"""
		This will consolidate contiguous ranges to make things more
		efficient.

		:returns None:
		:rtype: None
		"""
		copy = []
		previous_start = 0
		previous_end = 0

		for start, end in self.target_ranges:
			if start != previous_end:  # non-contiguous, output previous range
				if previous_start != previous_end:
					copy.append((previous_start, previous_end))
				previous_start = start
			else:   # contiguous regions, include this range in the previous one
				# we do this by updating the previous end, but not the previous start
				pass
			previous_end = end
		copy.append((previous_start, previous_end))
		self.target_ranges = copy

	def _start_program(self, args=None):
		"""
		This starts the target program, grabs the output and extracts
		the name of the target as reported by gdb.  This is saved to
		self.program_name so it can be used to find the process, as
		well as the sections from /proc/$pid/maps.  If, for some
		reason, the program name can not be extracted, a GdbException
		will be raised.  This method will block until a breakpoint
		is hit or a signal is caught, so make sure to place a
		breakpoint before calling this!

		:param args: The arguments to send to the target executable
		:type args: list of strings, or None
		:returns: the full response from gdb when the program is run
		:rtype: string
		"""
		info("Running target executable")
		if args:
			response = g.run(args=args, read_to_prompt=True)
		else:
			response = g.run(read_to_prompt=True)
		i = response.find("Starting program: ")
		if i < 0:
			raise GdbException("Unable to start program: %s" % response)
		i += 19  # the length of "Starting program: "
		self.program_name = response[i:response.find("\n", i)]
		return response

	def trace(self, outfile, args=None):
		"""
		This will start tracing a process, starting at the entry
		point.

		:param outfile: The file object where we should write the trace
		:type outfile: IOBase
		:param args: The arguments to pass to the target executable
		:type args: list of strings
		:returns: None
		:rtype: None
		"""
		self.set_disassembly_flavor()
		entry_point = self.get_target_info()

		debug("Setting breakpoint at *0x%x" % entry_point)
		breakpoint_number, addr = g.set_breakpoint("*0x%x" % entry_point)
		debug("Breakpoint #%d has been placed at %s" % (breakpoint_number, addr))

		response = self._start_program(args)  # this will run to the entry point
		response = self._determine_pc()       # program needs to be running before we can do this

		# We're currently at the entry point, we want to step forward
		# until we see the call to __libc_start_main
		info("Running executable to __libc_start_main")
		tmp = self._send_command("x/i $%s" % self.pc)
		while "__libc_start_main" not in tmp or "call" not in tmp:
			self.next_instruction()
			tmp = self._send_command("x/i $%s" % self.pc)

		arg0 = self.get_argument(0)
		info("__libc_start_main hit.  Running to 0x%x" % arg0)
		debug("Setting breakpoint at *0x%x" % arg0)
		breakpoint_number, addr = g.set_breakpoint("*0x%x" % arg0)
		debug("Breakpoint #%d has been placed at %s" % (breakpoint_number, addr))

		# And now we can run to that breakpoint adn begin tracing from there
		info("main() hit.  Tracing...")
		self.continue_execution(read_to_prompt=True)  # we'll hit a breakpoint
		self._trace(outfile)
		self.quit()

	def _trace(self, outfile):
		"""
		This actually implements the tracing through each instruction.
		It assumes that the program has been started, is at a breakpoint,
		that we know what register contains the program counter, and we
		have the ranges which contain the executable.  All that's left
		for this function is to examine instructions and step into or
		over each instruction until the program exits.

		:param outfile: The file object where we should write the trace
		:type outfile: IOBase
		:returns: None
		:rtype: None
		"""
		while True:  # this is horrible, but Python STILL doesn't have a post-test loop :-(
			pc = self.info_registers([self.pc])[self.pc]

			# We tried going to the next instruction when we're not
			# in Kansas anymore, to avoid going into CALLs which
			# are in some library, and thus be more efficient.
			# However, main() is a function which is called from
			# some library (libc, specifically __libc_start_main())
			# So, we need to actually step into each instruction
			# and then look at the program counter to know if we
			# should print the program counter or not.
			if not self._we_are_not_in_kansas_anymore(pc):
				outfile.write("%x\n" % pc)
				response = self.step_instruction()
			else:
				response = self._send_command("finish")

			if "exited normally" in response or \
				"received signal" in response or \
				"terminated with signal" in response:
				break

	def _we_are_not_in_kansas_anymore(self, pc):
		"""
		This will determine if we're still in the target binary or
		if we've JMPed/CALLed off into some library.

		:param pc: The location were we're currently broken
		:type pc: int
		:returns: True if we're off in some library, False otherwise
		:rtype: bool
		"""
		for start, end in self.target_ranges:
			if pc >= start and pc <= end:
				return False
		return True

if __name__ == "__main__":
	parser = ArgumentParser(description='Traces all branches in a program')
	parser.add_argument('executable', help=('The program to run'))
	parser.add_argument('--output-file', default=None,
				help=('The filename where we should write out the trace (Default: stdout)'))
	parser.add_argument('--target-args', default="", help="The arguments to pass to the target binary")
	parser.add_argument('-v', action='store_true',
	                    help=('Verbose output (for debugging issues)'))
	args = parser.parse_args()

	basicConfig(level=(INFO, DEBUG)[args.v], format="[%(levelname)5s] %(asctime)s - %(message)s")
	if args.output_file:
		outfile = open(args.output_file, "w")
	else:
		outfile = stdout

	try:
		g = GdbTracer(args.executable)
		g.trace(outfile, args.target_args.split(" "))
	except GdbException as e:
		error(str(e))
