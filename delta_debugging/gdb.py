#!/usr/bin/env python3
from argparse import ArgumentParser
from logging import debug, info, error, basicConfig, INFO, DEBUG
from select import select
from subprocess import Popen, PIPE, STDOUT

class GdbException(Exception):
	pass

class Gdb(object):
	def __init__(self, executable=None, discard_output=True, args=None, prompt="(gdb) "):
		"""
		This will start an instance of gdb.  By default, it will
		consume and discard any information read in before the
		prompt.  To keep this output in the buffer so it can be
		read in manually, set keep_output to True.  If any extra
		arguments are desired, they can be passed in as well.  If
		your system uses a non-standard prompt, this can be
		specified.

		:param executable: The program to load for debugging
		:type executable: string
		:param discard_output: If true, the info before the gdb prompt
				will be read (and discarded)
		:type discart_output: bool
		:param args: Any additional argument to pass in on the CLI
		:type args: list of strings
		:param prompt: The gdb prompt that your system uses
		:type prompt: string
		"""
		self.prompt = prompt

		_args = ["gdb", "-q", "-nx"] # quiet, don't execute ~/.gdbinit
		if args:
			debug("args = %s" % repr(args))
			_args.extend(args)
		if executable:
			_args.append(executable)

		self.p = Popen(_args, bufsize=0, universal_newlines=True, stdin=PIPE, stdout=PIPE, stderr=STDOUT)
		if discard_output:
			self.read_to_prompt()

	def read(self):
		"""
		This will read all available output from gdb.  This may include
		the gdb prompt (if gdb is, in fact, waiting for input).  This
		is a non-blocking call.  Normally you will probably want to use
		read_to_prompt() instead of this function.  This function comes
		in handy when you want to read the output after doing something
		which you do not expect to return (such as "run").

		:returns: The output of GDB (potentially including the prompt)
		:rtype: string
		"""
		data = ""

		while self.p.stdout in select([self.p.stdout], [], [], 0)[0]:
			line = self.p.stdout.readline()
			if line == "": # Nothing left to read
				break
			data += line

		return data

	def read_to_prompt(self):
		"""
		This will read the output from gdb up to the prompt.
		This is a blocking call, so it will hold up execution
		until something happens to interrupt the debugger (a
		breakpoint, signal, etc.) which causes the gdb prompt
		to be displayed.

		:returns: The output of GDB, excluding the prompt
		:rtype: string
		"""
		data = ""
		line = ""

		while line != self.prompt:
			try:
				line += self.p.stdout.read(1)
				if line.endswith("\n"):
					data += line
					line = ""
			except UnicodeDecodeError:
				pass  # gdb is spitting out garbage, ignore it

		return data

	def quit(self):
		"""
		Quit GDB

		:returns: None
		:rtype: None
		"""
		self._send_command("quit", read_to_prompt=False)
		self.p = None

	def set_breakpoint(self, symbol):
		"""
		This will place a breakpoint at the symbol.  The symbol could
		also be a dereference hex address (e.g. "*0xDEADBEEF").  If
		the breakpoint was successfully added, this will return the
		breakpoint number.  If it could not be loaded, for example if
		the symbol could not be found, a GdbException will be raised.

		:param symbol: The symbol or dereferenced hex address where
				the breakpoint should be placed.
		:type symbol: string
		:returns: Tuple of the breakpoint number and the address
		:rtype: Tuple of (int, string)
		"""
		cmd = "b %s" % symbol
		response = self._send_command(cmd)
		if not response.startswith("Breakpoint "):
			raise GdbException(response)
		parts = response.strip().split(" ")
		num = int(parts[1])
		addr = parts[3]
		return num, addr

	def _determine_pc(self):
		"""
		This will determine what register holds the program counter
		(e.g. rip, eip, pc, etc.) and save this variable name to
		self.pc.  If we are unable to determine the name of the
		program counter register, we will raise a GdbException.

		:returns: The full response from "info registers"
		:rtype: string
		"""
		response = self.info_registers()
		if "rip" in response:
			self.pc = "rip"
		elif "eip" in response:
			self.pc = "eip"
		elif "pc" in response:
			self.pc = "pc"
		else:
			raise GdbException("Unable to determine name of program counter register")
		debug("Program counter register is: %s" % self.pc)
		return response

	def get_argument(self, index):
		"""
		This will get the argument to a function.  On AMD64, this will
		return the contents of RDI for the 0th argument; on ARM, it'll
		return R0; and so on.

		:param index: The argument number you want
		:type index: int
		:returns: The value passed in the requested argument
		:rtype: int
		"""
		if self.pc == "rip":
			if index == 0:
				return self.info_registers(["rdi"])["rdi"]
			else:
				raise GdbException("get_argument only implemented for arg 0")
		else:
			raise GdbException("get_argument currently only implemented for AMD64")

	def run(self, args=None, read_to_prompt=False):
		"""
		This will run the executable passed in via the constructor.
		If any command line arguments should be passed to the target
		binary, they can be specified.

		:param args: The arguments to pass to the target executable
		:type args: list of strings
		:param read_to_prompt: Should the output be read & returned, or
				should it be left in the output buffer?
		:type read_to_prompt: bool
		:returns: If read_to_prompt is True, output from gdb will be
				returned.  Otherwise and empty string
				will be returned.
		:rtype: string
		"""
		cmd = "r"
		if args:
			cmd += " %s" % " ".join(args)
		return self._send_command(cmd, read_to_prompt)

	def continue_execution(self, read_to_prompt=False):
		"""
		This will continue execution.

		:param read_to_prompt: Should the output be read & returned, or
				should it be left in the output buffer?
		:type read_to_prompt: bool
		:returns: If read_to_prompt is True, output from gdb will be
				returned.  Otherwise and empty string
				will be returned.
		:rtype: string
		"""
		return self._send_command("c", read_to_prompt)

	def target_remote(self, host, port):
		"""
		This will attach to a remote gdb server.

		:param port: This should be the host to connect to
		:type port: string
		:param host: This should be the port to connect to
		:type host: integer
		:returns: output from GDB
		:rtype: string
		"""
		response = self._send_command("target remote %s:%d" % (host, port))
		if "Connection timed out" in response:
			raise GdbException(response)
		return response

	def detach(self):
		"""
		This will detach from a remote gdb server.

		:returns: output from GDB
		:rtype: string
		"""
		return self._send_command("detach")

	def set_disassembly_flavor(self, value="intel", read_to_prompt=True):
		"""
		This will set the disassembly flavor.  Since the default in gdb
		is AT&T syntax, you'll probably only want to call this with a
		value of "intel" which is why we made this the default.

		:param value: The desired disassembly syntax (Default: intel)
		:type value: string
		:param read_to_prompt: Should the output be read & returned, or
				should it be left in the output buffer?
		:type read_to_prompt: bool
		:returns: The output from gdb, or an empty string if the output
				is not read.
		:rtype: string
		"""
		return self._set("disassembly-flavor", value)

	def next_instruction(self, read_to_prompt=True):
		"""
		This will go to the next assembly instruction without tracing
		into CALLs.

		:param read_to_prompt: Should the output be read & returned, or
				should it be left in the output buffer?
		:type read_to_prompt: bool
		:returns: The output from gdb, or an empty string if the output
				is not read.
		:rtype: string
		"""
		return self._send_command("nexti")

	def step_instruction(self):
		"""
		This will step ahead one assembly instruction.  This will dig
		into CALL instructions.  If you want to skip all CALL
		instructions, use next_instruction.

		:returns: The output from gdb
		:rtype: string
		"""
		return self._send_command("stepi")

	def info_registers(self, registers=None):
		"""
		This will get the values from one or more registers.  If no
		registers are specified, it will return results for all
		registers.

		:param registers: The register(s) you are interested in (None
				for all registers, Default: None)
		:type registers: list of strings
		:returns: The contents of all requested registers
		:rtype: dictionary, keys are register names
		"""
		args = ["registers"]
		if registers:
			args.extend(registers)
		response = self._info(args)
		retval = {}
		for line in response.splitlines():
			parts = line.split()
			retval[parts[0]] = int(parts[1], 16)
		return retval

	def _info(self, args):
		"""
		This is a helper function used to get info from gdb.

		:param args: The arguments to the info command
		:type args: list of strings
		:returns: The output from gdb
		:rtype: string
		"""
		return self._send_command("info %s" % " ".join(args))

	def _set(self, var, value, read_to_prompt=True):
		"""
		This is a helper function used to set variables in gdb.

		:param var: The name of the variable you wish to set
		:type var: string
		:param value: The value you wish to assign to this variable
		:type value: string
		:param read_to_prompt: Should the output be read & returned, or
				should it be left in the output buffer?
		:type read_to_prompt: bool
		:returns: The output from gdb, or an empty string if the output
				is not read.
		:rtype: string
		"""
		return self._send_command("set %s %s" % (var, value), read_to_prompt=True)

	def _send_command(self, cmd, read_to_prompt=True):
		"""
		This will send a command to gdb and then read the output until
		it gets a prompt, unless instructed otherwise.

		:param cmd: The command to send to GDB
		:type cmd: string
		:param read_to_prompt: Should the output be read & returned, or
				should it be left in the output buffer?
		:type read_to_prompt: bool
		:returns: The output from gdb, or an empty string if the output
				is not read.
		:rtype: string
		"""
		return self.send_input("%s\n" % cmd, read_to_prompt).strip()

	def send_EOF(self, read_to_prompt=True):
		"""
		This will send an EOF (end of file) character to gdb.  If the
		target executable is running, this will be sent to that program.
		If it is at a breakpoint, gdb will process the input.

		:param read_to_prompt: Should the output be read & returned, or
				should it be left in the output buffer?
		:type read_to_prompt: bool
		:returns: The output from gdb, or an empty string if the output
				is not read.
		:rtype: string
		"""
		output = ""
		debug("Sending EOF GDB")
		self.p.stdin.close()
		if read_to_prompt:
			output = self.read_to_prompt()
		return output.strip()

	def send_input(self, data, read_to_prompt=True):
		"""
		This will send data to gdb.  If the target executable is
		running, this will be sent to that program.  If it is at
		a breakpoint, gdb will process the input as commands.

		:param data: The data to send to GDB
		:type data: string
		:param read_to_prompt: Should the output be read & returned, or
				should it be left in the output buffer?
		:type read_to_prompt: bool
		:returns: The output from gdb, or an empty string if the output
				is not read.
		:rtype: string
		"""
		output = ""
		debug("Sending data to GDB: %s" % data.strip())
		self.p.stdin.write("%s" % data)
		if read_to_prompt:
			output = self.read_to_prompt()
		return output.strip()

if __name__ == "__main__":
	parser = ArgumentParser(description='Runs a program under GDB')
	parser.add_argument('executable', help=('The program to run'))
	parser.add_argument('--breakpoint', default="main",
	                    help="The place where you'd like to place a breakpoint (Default: main)")
	parser.add_argument('--gdb-args', default="", help="The arguments to pass to gdb")
	parser.add_argument('--target-args', default="", help="The arguments to pass to the target binary")
	parser.add_argument('-v', action='store_true',
	                    help=('Verbose output (for debugging issues)'))
	args = parser.parse_args()

	basicConfig(level=(INFO, DEBUG)[args.v], format="[%(levelname)5s] %(asctime)s - %(message)s")

	try:
		if args.gdb_args:
			g = Gdb(args.executable, args=args.gdb_args.split(" "))
		else:
			g = Gdb(args.executable)

		info("Setting breakpoint")
		breakpoint_number = None
		try:
			breakpoint_number, addr = g.set_breakpoint(args.breakpoint)
			info("Breakpoint #%d has been placed at %s" % (breakpoint_number, addr))
		except GdbException as e:
			error("Unable to place breakpoint: %s" % str(e))

		info("Running target executable")
		response = g.run(args=args.target_args.split(" "), read_to_prompt=True)
		info(response)

		if breakpoint_number:
			info("Continuing execution")
			response = g.continue_execution(read_to_prompt=True)
			info(response)

		info("Quitting gdb")
		g.quit()
	except GdbException as e:
		error(str(e))
