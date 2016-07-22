#!/usr/bin/env python3
# author: grey@christoforo.net

import visa # https://github.com/hgrecco/pyvisa
#visa.log_to_screen() # for debugging
rm = visa.ResourceManager('@py') # select pyvisa-py (pure python) backend

smAddressIP = '10.42.0.60' # IP address of sourcemeter
smAddress = 'TCPIP::'+smAddressIP+'::INSTR'
#smAddress = 'TCPIP::'+smAddressIP+'::5025::SOCKET' # for raw TCPIP comms directly through a socket @ port 5025 (probably worse than INSTR)
print("Connecting to "+smAddress+"...")
try:
  sm = rm.open_resource(smAddress) # connect to sourcemeter
except:
  print("Unable to connect to "+smAddress)
  exit()
print("Connected.")
print("Address:")
print(sm._resource_name)

#sm.read_termination = u'\n' # needed only for SOCKET type connection
sm.write("*IDN?") # ask the instrument to identify its self

idnString = sm.read(termination = u'\n')
idnFields = idnString.split(',')
idnFieldsExpected = ['KEITHLEY INSTRUMENTS', 'MODEL 2450', '04085562', '1.5.0g']
# this software has been tested with a Keithley 2450 sourcemeter with firmware version 1.5.0g
# your milage may vary if you try to use anything else

print("Instrument:")
print(idnFields)

sm.close() # close connection

