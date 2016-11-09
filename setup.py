#!/usr/bin/env python

from distutils.core import setup

setup(name = "delta_debugging",
      version = "1.10",
      description = "Delta Debugging - debugging library to generate minimal crashing test cases",
      author = ("Andreas Zeller, Martin Burger, " + 
                "Holger Cleve, Karsten Lehmann, Stephan Neuhaus, " +
                "and Tom Zimmermann.  Modified by Grimm."),
      author_email = "github@grimm-co.com",
      url = "https://github.com/grimm-co",
      packages = ["delta_debugging"],
      scripts = ["scripts/dd-return-code.py"]
      )
