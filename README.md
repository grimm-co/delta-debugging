Delta Debugging is a fantastic tool which will take a test case which crashes
a program and reduce it until you are left with the smallest file which still
causes the crash.  It is quite efficient at doing this and has a lot of
academic research backing it up.  More importantly, it is very practical in
the real world at helping triage crashes.

For more info, check out their site:
https://www.st.cs.uni-saarland.de/dd/

This fork of DD is compatible with both Python 2 and 3 (original was written
for Python 2 and did not work in 3).  We also plan on making some scripts to
improve usability and reduce the amout of custom python code that needs to be
written and hopefully eliminate the need to write any custom code in most
cases.

