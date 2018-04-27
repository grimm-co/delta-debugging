#!/usr/bin/env python3
# This test script illustrates the 

try:
	from delta_debugging.DD import DD
except ImportError as e:
	print("Unable to import delta debugging library.  Please ensure it is "
		"installed.  https://github.com/grimm-co/delta-debugging")
	from sys import exit
	exit(-1)

class TestDD(DD):
	def __init__(self):
		DD.__init__(self)
		self.debug_dd = 0
		self.verbose = 0

	def _test(self, deltas):
		# Build input file
		found = []
		for (index, byte) in deltas:
			if byte == "1" or byte == "7" or byte == "8":
				found.append(byte)

		ret = self.PASS
		if found.count("1") == 1 and found.count("7") == 1 and found.count("8") == 1:
			ret = self.FAIL
		print('Testing case {:11}: {}'.format('"' + "".join([x[1] for x in deltas]) + '"', str(ret)))
		return ret

if __name__ == '__main__':
	test_input = "12345678"
	print('Minimizing input: "{}"'.format(test_input))

	# Convert string into the delta format
	deltas = list(map(lambda x: (x, test_input[x]), range(len(test_input))))

	mydd = TestDD()
	c = mydd.ddmin(deltas)              # Invoke DDMIN

	minimal = "".join([x[1] for x in c])
	print('Found minimal test case: "{}"'.format(minimal))

