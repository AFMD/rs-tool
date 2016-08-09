#!/usr/bin/env python3
# author: grey@christoforo.net

import sys
import ipaddress
import visa # https://github.com/hgrecco/pyvisa
import numpy

# debugging/testing stuff
import time
#visa.log_to_screen() # for debugging
import timeit

def main():
  # create a visa resource manager
  rm = visa.ResourceManager('@py') # select pyvisa-py (pure python) backend
  
  # ====for TCPIP comms====
  instrumentIP = ipaddress.ip_address('10.42.0.60') # IP address of sourcemeter
  fullAddress = 'TCPIP::'+str(instrumentIP)+'::INSTR'
  timeout = 1000 # ms
  #fullAddress = 'TCPIP::'+smAddressIP+'::5025::SOCKET' # for raw TCPIP comms directly through a socket @ port 5025 (probably worse than INSTR)
  openParams = {'resource_name':fullAddress, 'timeout': timeout, '_read_termination': u'\n'}
  
  # ====for serial rs232 comms=====
  #serialPort = "/dev/ttyUSB0"
  #fullAddress = "ASRL"+serialPort+"::INSTR"
  #timeout = 1000 # ms
  #sm = rm.open_resource(smAddress)
  #sm.set_visa_attribute(visa.constants.VI_ATTR_ASRL_BAUD,57600)
  #sm.set_visa_attribute(visa.constants.VI_ASRL_END_TERMCHAR,u'\r')
  #openParams = {'resource_name':fullAddress, 'timeout': timeout}
  
  # form a connection to our sourcemeter
  sm = visaConnect(rm, openParams)

  # setup for sweep
  setupSweep(sm)
  
  print("Done!")  
  sm.close() # close connection
  
def setupSweep(sm):
  maxCurrent = 0.05 # amps
  sweepStart = -0.003 #volts
  sweepEnd = 0.003 # volts
  nPoints = 1001
  #stepDelay = -1 # seconds (-1 for auto delay)
  stepDelay = 0 # seconds (-1 for auto delay)
  sm.write("*RST")
  sm.write("*LANG SCPI")
  sm.write(":FORMAT:DATA REAL")
  sm.write(':SOURCE1:FUNCTION VOLTAGE')
  sm.write(':SOURCE1:VOLTAGE:RANGE {:}'.format(max(map(abs,[sweepStart,sweepEnd]))))
  sm.write(':SOURCE1:VOLTAGE:ILIMIT {:}'.format(maxCurrent))
  sm.write(':SENSE1:FUNCTION "CURRENT"')
  sm.write(':SENSE1:CURRENT:RANGE {:}'.format(maxCurrent))
  sm.write(":SENSE1:CURRENT:RSENSE 1") # enable four wire mode
  sm.write(':SOURCE1:SWEEP:VOLTAGE:LINEAR {:}, {:}, {:}, {:}'.format(sweepStart,sweepEnd,nPoints,stepDelay))
  
  # here are a few settings that trade accuracy for speed
  sm.write(':SENSE1:CURRENT:AZERO:STATE 0') # disable autozero
  sm.write(':SENSE1:CURRENT:NPLC 0.01') # set NPLC
  sm.write(':SOURCE1:VOLTAGE:READ:BACK OFF') # disable voltage readback
  
  # do one auto zero manually is the manual autozero sequence (could take over a second)
  sm.write(':SENSE1:AZERO:ONCE') # do one autozero now
  oldTimeout = sm.timeout
  sm.timeout = 5000
  sm.query('*STB?') # ask for the status bit
  sm.timeout=oldTimeout
  
  #sm.write():
  
  # make up a timeout for this sweep
  # here we assume one measurement takes no longer than 100ms
  # and the initial setup time is 500ms
  # this value might become an issue (not big enough) if averaging or high NPLC is configured
  if stepDelay is -1: 
    stepDelay = 0
  sm.timeout = 500 + round(nPoints*(stepDelay*1000+100))  
  
  # trigger the reading
  sm.write('INIT') #should be: sm.assert_trigger()
  sm.write('*WAI') # no other commands during this sweep
  #sm.values_format.use_binary('d', False, numpy.array)
  message = 'TRACE:DATA? {:}, {:}, "defbuffer1", SOUR, READ'.format(1,nPoints) # form the "ask for buffer" message
  
  # ask for the contents of the sweep buffer
  t = time.time()
  values = sm.query_binary_values(message, datatype='d', is_big_endian=False, container=numpy.array, delay=None, header_fmt='ieee')
  elapsed=time.time()-t
  print ("Elapsed =",elapsed*1000)
  sm.timeout = oldTimeout

  values = values.reshape([-1,2])
  v = values[:,0]
  i = values[:,1]
  #print(v)
  #print(i)

  #sm.write(':SENSE1:AVERAGE OFF')
  #sm.write(':SENSE1:CURR:NPLC 1')
  #sm.write(':SENSE1:FUNC:CONC OFF')
  #sm.write(':OUTP ON')
  #sm.write(':SENSE1:AZERO:ONCE')
  
  
  #sm.write(":FORMAT:DATA REAL")
  #print(sm.query_binary_values('READ?'))
  
  #sm.write(":FORMAT:DATA REAL")
  #values = sm.query_binary_values('CURV?', datatype='d', is_big_endian=True)
  #sm.values_format.use_binary('d', True, numpy.array)
  #sm.write('CURV?')
  #data = sm.read_raw()
  #print(data)
  #data = sm.read_values()
  #print(data)
  #sm.write(':SENS:AVER OFF')
  
  #sm.write(':SENS:FUNC:CONC OFF')
  #sm.write(':SYST:AZER ON')
  #sm.write(':SOUR:DEL:AUTO ON')
  #sm.write(':SOUR:FUNC VOLT')
  #sm.write(':SENS:FUNC "CURR:DC"')
  #sm.write(':SENS:CURR:NPLC 1')
  
  #print (sm.query("*IDN?"))

# connects to a instrument/device given a resource manager and some open parameters
def visaConnect (rm, openParams):
  fullAddress = openParams['resource_name']
  print("Connecting to", fullAddress, "...")
  try:
    d = rm.open_resource(**openParams) # connect to device
  except:
    print("Unable to connect via", fullAddress)
    exctype, value = sys.exc_info()[:2]
    print(value)
    exit()
  print("Connection established.")
  
  try:
    # ask the device to identify its self
    idnString = d.query("*IDN?")
  except:
    print('Unable perform "*IDN?" query.')
    exctype, value = sys.exc_info()[:2]
    print(value)    
    d.close()
    exit() 
  
  #idnFields = idnString.split(',')
  #idnFieldsExpected = ['KEITHLEY INSTRUMENTS', 'MODEL 2450', '04085562', '1.5.0g']
  # this software has been tested with a Keithley 2450 sourcemeter with firmware version 1.5.0g
  # your milage may vary if you try to use anything else
  
  print("Device identified as:")
  print(idnString)
  
  return d

if __name__ == "__main__":
  main()
