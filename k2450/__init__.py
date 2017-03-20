import sys
import numpy
import time # for finding the sample frequency
import socket # this is for testing if a TCPIP connection is pre-existing

def printEventLog(sm):
  errorCount = 0
  while True:
    errorString = sm.query(':SYSTEM:EVENTLOG:NEXT?')
    errorSplit = errorString.split('"')
    errorNum = int(errorSplit[0].split(',')[0])
    if errorNum == 0:
      break # no error
    else:
      errorCount = errorCount + 1
      errorSubSplit = errorSplit[1] # toss quotations
      errorSubSplit = errorSubSplit.split(';')
      print(errorSubSplit[2], errorSubSplit[0],"TYPE",errorSubSplit[1],)
  sm.write(':SYSTEM:CLEAR') # clear the logs since we've read them now
  if errorCount == 0:
    print('No errors in log.')
    

# connects to a instrument/device given a resource manager and some open parameters
def visaConnect (rm, openParams):
  print("Connecting to", openParams['resource_name'], "...")
  if 'TCPIP::' in openParams['resource_name']:
    ip = openParams['resource_name'].split('::')[1]
    try: # let's try to open a connection to the instrument on port 1024 then 111...
      s = socket.create_connection((ip,1024),timeout=openParams['timeout']/1000)
      s.shutdown(socket.SHUT_RDWR)
      s.close()
      del(s)
      s = socket.create_connection((ip,111))
      s.shutdown(socket.SHUT_RDWR)
      s.close()
      del(s)
    except:
      print("Error: Unable to open a socket to", ip)
      exctype, value = sys.exc_info()[:2]
      print(value)
      return None
  try:
    d = rm.open_resource(**openParams) # connect to device
  except:
    print("Unable to connect via", openParams['resource_name'])
    exctype, value = sys.exc_info()[:2]
    print(value)
    return None
  print("Connection established.")
  
  print("Querying device type...")
  try:
    # ask the device to identify its self
    idnString = d.query("*IDN?")
  except:
    print('Unable perform "*IDN?" query.')
    exctype, value = sys.exc_info()[:2]
    print(value)
    try:
      d.close()
    except:
      pass
    return None
  
  #idnFields = idnString.split(',')
  #idnFieldsExpected = ['KEITHLEY INSTRUMENTS', 'MODEL 2450', '04085562', '1.5.0g']
  # this software has been tested with a Keithley 2450 sourcemeter with firmware version 1.5.0g
  # your milage may vary if you try to use anything else
  
  print("Device identified as",idnString)
  
  return d

# basic setup tasks for a keithley 2450
def setup2450(sm):
  sm.write("*RST")
  sm.write(":TRACE:CLEAR") # clear the defualt buffer ("defbuffer1")
  sm.write("*CLS") # clear status & system logs and associated registers
  sm.write("*SRE {:}".format((1<<2) + (1<<4))) # enable error reporting via status bit (by setting EAV bit)
  sm.write("*LANG SCPI")
  
  # setup for binary (superfast) data transfer
  sm.write(":FORMAT:DATA REAL")
  sm.values_format.container = numpy.array
  sm.values_format.datatype = 'd'
  return True # setup completed properly

# returns number of milliseconds to use for the sweep timeout value
def estimateSweepTimeout(nPoints,stepDelay,nplc):
  # let's estimate how long the sweep will take so we know when to time out
  # here we assume one measurement takes no longer than 100ms
  # and the initial setup time is 500ms
  # this will break if NPLC and averaging are not their default values
  # TODO: take into account averaging, autozero to make a better estimate
  powerlineAssumption = 50 # Hz
  cycleTime = 1/powerlineAssumption # seconds
  fudgeFactor = 4 # don't know why I need this
  measurementTime = nplc * cycleTime * fudgeFactor # seconds
  if stepDelay is -1:
    localStepDelay = 0
  else:
    localStepDelay = stepDelay
  estimate = 500 + round(nPoints*(localStepDelay*1000+measurementTime*1000))
  #print ('Sweep Estimate [ms]: {:}'.format(estimate))
  return estimate
  
# setup 2450 for sweep returns True on success
def configureSweep(sm,sweepParams):
  sm.write(':SOURCE1:FUNCTION {:}'.format(sweepParams['sourceFun']))
  sm.write(':SOURCE1:{:}:RANGE {:}'.format(sweepParams['sourceFun'],max(map(abs,[sweepParams['sweepStart'],sweepParams['sweepEnd']]))))
  sm.write(':SOURCE1:{:}:ILIMIT {:}'.format(sweepParams['sourceFun'],sweepParams['maxCurrent']))
  sm.write(':SENSE1:FUNCTION "{:}"'.format(sweepParams['senseFun']))
  sm.write(':SENSE1:{:}:RANGE {:}'.format(sweepParams['senseFun'],sweepParams['maxCurrent']))
  if sweepParams['fourWire']:
    sm.write(':SENSE1:{:}:RSENSE ON'.format(sweepParams['senseFun']))# rsense (remote voltage sense) ON means four wire mode
  else:
    sm.write(':SENSE1:{:}:RSENSE OFF'.format(sweepParams['senseFun']))# rsense (remote voltage sense) ON means four wire mode
  sm.write(':ROUTE:TERMINALS FRONT')
  sm.write(':SOURCE1:{:}:LEVEL:IMMEDIATE:AMPLITUDE {:}'.format(sweepParams['sourceFun'],sweepParams['sweepStart'])) # set output to sweep start voltage
  
  # do one auto zero manually (could take over a second)
  oldTimeout = sm.timeout
  sm.timeout = 5000
  if not sweepParams['autoZero']:
    sm.write(':SENSE1:AZERO:ONCE') # do one autozero now
    sm.write(':SENSE1:{:}:AZERO OFF'.format(sweepParams['senseFun']))
  else:
    sm.write(':SENSE1:{:}:AZERO ON'.format(sweepParams['senseFun'])) # do autozero on every measurement
  sm.write('*WAI') # no other commands during this
  opc = sm.query('*OPC?') # wait for the operation to complete
  sm.timeout=oldTimeout  
  
  # here are a few settings that trade accuracy for speed
  #sm.write(':SENSE1:CURRENT:AZERO:STATE 0') # disable autozero for future readings
  sm.write(':SENSE1:NPLC {:}'.format(sweepParams['nplc'])) # set NPLC
  #sm.write(':SOURCE1:VOLTAGE:READ:BACK OFF') # disable voltage readback
  
  # turn on the source and wait for it to settle
  sm.write(':OUTPUT1:STATE ON')
  sm.write('*WAI') # no other commands during this
  opc = sm.query('*OPC?') # wait for the operation to complete
  
  if checkStatus(sm):
    return False
  
  # setup the sweep
  sm.write(':SOURCE1:SWEEP:{:}:LINEAR {:}, {:}, {:}, {:}'.format(sweepParams['sourceFun'],sweepParams['sweepStart'],sweepParams['sweepEnd'],sweepParams['nPoints'],sweepParams['stepDelay']))
  
  stb = sm.query('*STB?') # ask for the status byte
  if checkStatus(sm):
    return False  
  else:
    return True
  

  
def doSweep(sm):
  # check that things are cool before we do the sweep
  if checkStatus(sm):
    return False
  
  print ("Sweep initiated...")
  # trigger the sweep
  sm.write(':INITIATE:IMMEDIATE') #should be: sm.assert_trigger()
  sm.write('*WAI') # no other commands during this
  return True

# returns true if event
def checkStatus(sm):
  stb = int(sm.query('*STB?')) # ask for the status byte
  if stb not in(0,64):
    print ("Status byte value:", stb)
    printEventLog(sm)
    return True
  else:
    return False
    

def fetchSweepData(sm,sweepParams):
  oldTimeout = sm.timeout
  sm.timeout = sweepParams['durationEstimate']
  t = time.time()
  #TODO: should rely on SRQ here rather than read with timeout
  opc = sm.query('*OPC?') # wait for any pending operation to complete
  elapsed=time.time()-t
  sm.timeout = oldTimeout
  nReadings = int(sm.query(':TRACE:ACTUAL?'))
  print ("Sweep complete!")
  print ("Sample frequency = {:.1f} Hz".format(nReadings/elapsed))
  print ("Sweep event Log:")
  printEventLog(sm)
  
  if nReadings != sweepParams['nPoints']: # check if we got enough readings
    print("Error: We expected", sweepParams['nPoints'], "data points, but the Keithley's data buffer contained", nReadings)
    return (None,None)
  
  # ask keithley to return its buffer
  values = sm.query_values ('TRACE:DATA? {:}, {:}, "defbuffer1", SOUR, READ'.format(1,sweepParams['nPoints']))
  sm.write(":TRACE:CLEAR") # clear the buffer now that we've fetched it

  # reformat what we got back  
  values = values.reshape([-1,2])
  v = values[:,0]
  i = values[:,1]
  
  return (i,v)
