import sys
import numpy
import time # for finding the sample frequency
import socket # this is for testing if a TCPIP connection is pre-existing
import types
import struct
import math

MSB = 1<<0 # message summary bit
EAV = 1<<2 # error available bit
QSB = 1<<3 # questionable summary bit
MAV = 1<<4 # message available bit
ESB = 1<<5 # event summary bit
MSS = 1<<6 # master summary status bit
OSB = 1<<7 # operation summary bit

# SOUR status bits
SS_OVP = 1<<2 # Overvoltage protection was active
SS_MES = 1<<3 # Measured source value was read
SS_OVT = 1<<4 # Overtemperature condition existed
SS_LIM = 1<<5 # Source function level was limited
SS_4WS = 1<<6 # Four-wire sense was used
SS_OON = 1<<7 # Output was on

def printErrors(sm):
  errorCount = int(sm.query(':SYSTem:ERRor:COUNt?'))
  while errorCount > 0:
    print(sm.query('SYST:ERR:NEXT?'))
    errorCount = int(sm.query(':SYSTem:ERRor:COUNt?'))
    
def getEvents(sm, pr=False):
  eventCount = int(sm.query(':SYSTem:EVENtlog:COUNt?'))
  eventNums = []
  while eventCount > 0:
    event = sm.query('SYSTem:EVENtlog:NEXT?')
    eventSplit = event.split(',')
    eventNums.append(int(eventSplit[0]))
    if pr:
      print(event)
    eventCount = int(sm.query(':SYSTem:EVENtlog:COUNt?'))
  return eventNums
    
def printErrors(sm):
  errorCount = int(sm.query(':SYSTem:ERRor:COUNt?'))
  while errorCount > 0:
    print(sm.query('SYST:ERR:NEXT?'))
    errorCount = int(sm.query(':SYSTem:ERRor:COUNt?'))

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



class socketConn:
  def __init__(self, s=None):
    self.s = s
    self.termChar = b'\n'
    self.decode = 'utf-8'
    self.getLen = 4096
    self.values_format = types.SimpleNamespace()
    self.values_format.container = numpy.array
    self.values_format.datatype = 'd'
    self.timeout = s.timeout
    try: # this will clear all pending data
      rcv = None
      while rcv == b'':
        rcv = s.recv(self.getLen)
    except:
      pass
  
    
  def __del__(self):
    self.s.shutdown(socket.SHUT_RDWR)
    self.s.close()
    del(self.s)
    
  def close(self):
    self.write('OUTPut OFF')
  
  # serial poll routine until we get one of the requested status bits set
  # or until a non-zero status byte or until we timeout
  def spoll(self, request):
    byte = int(self.query('*STB?'))
    start = time.time()
    elapsed = time.time() - start
    while (not byte & request) and elapsed < self.timeout:
      byte = int(self.query('*STB?'))
      print(byte)
      if byte & (MAV | EAV): # handle events
        printEvents(self)
      elapsed = time.time() - start
    return byte
  
  def write(self,string):
    toSend = bytes(string,self.decode) + self.termChar
    #nToSend = len(toSend)
    ret = self.s.sendall(toSend)
    if ret == None:
      return True
    else:
      return False
  
  def read(self,string=True):
    self.s.setblocking(False)
    buf = b''
    while self.termChar not in buf:
      try:
        buf += self.s.recv(self.getLen)
      except BlockingIOError:
        pass
    self.s.setblocking(True)
    if string == True:
      ret = buf.decode(self.decode)
      return ret.rstrip()
    else:
      return buf.rstrip().lstrip(b'#0')
    
  def query(self,string):
    if self.write(string):
      return self.read()
    else:
      return None
    
  def query_values(self,string):
    buf = b''
    if self.write(string):
      result = self.read(string=False)
      unpacker = struct.iter_unpack('d',result)
      return numpy.array(list(unpacker))
    else:
      return None    
    
    

# connects to a instrument/device given a resource manager and some open parameters
def visaConnect (rm, openParams):
  print("Connecting to", openParams['resource_name'], "...")
  if 'TCPIP::' in openParams['resource_name']:
    ip = openParams['resource_name'].split('::')[1]
    try: # let's try to open a connection to the instrument on port 5025 (SOCKET), 1024(VXI-11) then 111...
      s = socket.create_connection((ip,5030),timeout=openParams['timeout']/1000) # dead socket kills all previous connections
      s.shutdown(socket.SHUT_RDWR)
      s.close()
      del(s)      
      s = socket.create_connection((ip,1024),timeout=openParams['timeout']/1000)
      s.shutdown(socket.SHUT_RDWR)
      s.close()
      del(s)
      s = socket.create_connection((ip,111))
      s.shutdown(socket.SHUT_RDWR)
      s.close()
      del(s)
      s = socket.create_connection((ip,5025))
      s.shutdown(socket.SHUT_RDWR)
      s.close()
      del(s)      
    except:
      print("Error: Unable to open a socket to", ip)
      exctype, value = sys.exc_info()[:2]
      print(value)
      return None   
  if 'SOCKET' in openParams['resource_name']:
    s = socket.create_connection((ip,5025),timeout=openParams['timeout']/1000) # open a socket
    d = socketConn(s)
  else:
    try:
      d = rm.open_resource(**openParams) # connect to device
    except:
      print("Unable to connect via", openParams['resource_name'])
      exctype, value = sys.exc_info()[:2]
      print(value)
      return None
  print("Connection established.")
  
  print("Resetting Device...")
  try:
    res = d.query("*RST; *CLS; *ESE 32; *OPC?")
    if res is not '1':
      raise
    print("Done.")
  except:
    print("Unable perform device reset")
    exctype, value = sys.exc_info()[:2]
    print(value)
    try:
      d.close()
    except:
      pass
    return None
  
  #byte = int(d.query('*STB?'))
  #pollret = d.spoll(OSB)
  
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
  fudgeFactor = 10 # don't know why I need this
  measurementTime = nplc * cycleTime * fudgeFactor # seconds
  if stepDelay is -1:
    localStepDelay = 0
  else:
    localStepDelay = stepDelay
  estimate = 500 + round(nPoints*(localStepDelay*1000+measurementTime*1000))
  print ('Sweep Estimate [ms]: {:}'.format(estimate))
  return estimate

# sweep through some source current values and measure v to find R
def rSweep(sm, rsOpt):
  sm.write('SENSE:NPLC {:}'.format(rsOpt['nplc']))
  sm.write('SENSe:FUNCtion "VOLT"')
  sm.write('SENSe:VOLTage:RANGe:AUTO ON')
  sm.write('SENSe:VOLTage:UNIT OHM')
  
  if not rsOpt['autoZero']:
    sm.write(':SENSe:AZERO:ONCE') # do one autozero now
    sm.write(':SENSe:VOLTage:AZERO OFF')
  else:
    sm.write(':SENSe:VOLTage:AZERO ON') # do autozero on every measurement
  
  if rsOpt['oCom']:
    sm.write('SENSe:VOLTage:OCOM ON')
  else:
    sm.write('SENSe:VOLTage:OCOM OFF')
  
  if rsOpt['fourWire']:
    sm.write(':SENSE1:VOLTage:RSENSE ON')# rsense (remote voltage sense) ON means four wire mode
  else:
    sm.write(':SENSE:VOLTage:RSENSE OFF')# rsense (remote voltage sense) ON means four wire mode
    
  sm.write('SOURce:FUNCtion CURR')
  if rsOpt['stepDelay'] != '-1':
    sm.write('SOURce:CURRent:DELAY:AUTO OFF')
    sm.write('SOURce:CURRent:DELAY {:}'.format(float(rsOpt['stepDelay'])))
  else:
    sm.write('SOURce:CURRent:DELAY:AUTO ON')
  sm.write('SOURce:CURRent {:}'.format(rsOpt['iMax']))
  sm.write('SOURce:CURRent:VLIM {:}'.format(rsOpt['vLim']))
  preCount = 10
  sm.write('SENSe:COUNt {:}'.format(preCount))
  sm.write('OUTPut ON')
  sm.write('TRACe:TRIGger "defbuffer1"')
  
  status = int(sm.query('*STB?')) # this will return when the measurement is done
  if status != 0:
    events = getEvents(sm,pr=True)
  values = sm.query_values('TRACe:DATA? 1, {:}, "defbuffer1", SOUR, READ'.format(preCount))
  sm.write(":FORMAT:DATA ASCII")
  statiiA = sm.query('TRACe:DATA? 1, {:}, "defbuffer1", SOURSTAT'.format(preCount))
  statiiA = list(map(int,statiiA.split(',')))
  #print(statiiA)
  statii = sm.query('TRACe:DATA? 1, {:}, "defbuffer1", STAT'.format(preCount))
  statii = list(map(int,statii.split(',')))
  #print(statii)
  sm.write(":FORMAT:DATA REAL")
  
  sm.write(":TRACE:CLEAR")
  values = values.reshape([preCount,2])
  s = values[:,0]
  r = values[:,1]
  v = s*r
  vMin = v.min()
  if any(map (lambda x: SS_LIM & x,statiiA)):
    print('ERROR: Source voltage limit hit on one or more of our measurements.')
    print('Pro Tip: Reduce the max source current or increase the voltage limit.')
    return False
  elif vMin < 0.01:
    print('ERROR: A voltage measured was only {:}V'.format(vMin))
    print('Pro Tip: Consider increasing the max source current.')
    return False
  elif 0.1*s[1::].mean() < s[1::].std():
    print('ERROR: The source current was very unsteady across several measurements.')
    print('Pro Tip: Reduce the max source current.')
    return False
  else:
    newImax = s.mean()
    print('Preliminary values:')
    R = r.mean() # resistance
    rS = R*math.pi/math.log(2) # sheet resistance
    print ("R=", R,'+/-',R.std(),u" [\u03A9]")
    print ("R_s=",rS,u" [\u03A9/\u25AB]")
    
    print('Starting resistance sweep from {:} to {:} A'.format(newImax,-newImax))
    senseRange = float(sm.query('SENSe:VOLTage:RANGe?'))
    sm.write('SENSe:VOLTage:RANGe {:}'.format(senseRange))
    sm.write(':SYSTem:CLEar')
    #getEvents(sm,pr=False)
    sourceRange = float(sm.query('SOURCE:CURR:RANGe?'))
    sm.write('SOURCE:CURR:RANGe {:}'.format(sourceRange))
    sm.write('SENSe:VOLTage:UNIT VOLT')
    
    # setup the sweep
    sm.write(':SOURCE:SWEEP:CURR:LINEAR {:}, {:}, {:}, {:}, 1, fixed, {:}, ON, "defbuffer1"'.format(newImax,-newImax,rsOpt['nPoints'],rsOpt['stepDelay'],rsOpt['failAbort']))
      
#      sm.write('INIT')#do the sweep
#      sm.write('*WAI') # no other commands during this
#      status = int(sm.query('*STB?')) # this will return when the measurement is done
#      if status != 0:
#        events = getEvents(sm,pr=True)          
#
#      values = sm.query_values('TRACe:DATA? 1, {:}, "defbuffer1", SOUR, READ'.format(rsOpt['nPoints']*2-1))
#        
#  sm.write('OUTPut OFF')
  
  return True
  
  

# returns n auto ohms measurements
def measureR(sm, rOpt):
  #sm.write('*RST')
  
  sm.write('SENSE:NPLC {:}'.format(rOpt['nplc']))
  sm.write('SENSe:FUNCtion "RES"')
  sm.write('SENSe:RESistance:RANGe:AUTO ON')
  sm.write('SENSe:RESistance:OCOMpensated ON')
  sm.write('SENSe:COUNt {:}'.format(rOpt['n']))
  
  if rOpt['fourWire']:
    sm.write(':SENSE1:RESistance:RSENSE ON')# rsense (remote voltage sense) ON means four wire mode
  else:
    sm.write(':SENSE:RESistance:RSENSE OFF')# rsense (remote voltage sense) ON means four wire mode
  
  sm.write('OUTPut ON')
  time.sleep(1)
  sm.write('TRACe:TRIGger "defbuffer1"')
  sm.timeout = 500
  #pollRet = sm.spoll(ESB)
  values = sm.query_values('TRACe:DATA? 1, {:}, "defbuffer1", SOUR, READ'.format(rOpt['n']))
  autoSenseCurrent = float(sm.query("source:current:level?"))
  sm.write('source:current:level {:}'.format(autoSenseCurrent*-1))
  sm.write('OUTPut OFF')
  values = values.reshape([rOpt['n'],2])
  r = values[:,1]
  return r
  
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
  sm.write(':SOURCE1:SWEEP:{:}:LINEAR {:}, {:}, {:}, {:}, 1, {:}, {:}, {:}'.format(sweepParams['sourceFun'],sweepParams['sweepStart'],sweepParams['sweepEnd'],sweepParams['nPoints'],sweepParams['stepDelay'],sweepParams['rangeType'],sweepParams['failAbort'],sweepParams['dual']))
  
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
  #sm.timeout = sweepParams['durationEstimate']
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
  
  if nReadings != sweepParams['nPoints']*2-1: # check if we got enough readings
    print("Error: We expected", sweepParams['nPoints']*2-1, "data points, but the Keithley's data buffer contained", nReadings)
    return (None,None)
  
  # ask keithley to return its buffer
  values = sm.query_values ('TRACE:DATA? {:}, {:}, "defbuffer1", SOUR, READ'.format(1,sweepParams['nPoints']*2-1))
  sm.write(":TRACE:CLEAR") # clear the buffer now that we've fetched it

  # reformat what we got back  
  values = values.reshape([-1,2])
  i = values[0:sweepParams['nPoints'],0]
  v = values[0:sweepParams['nPoints'],1]
  i2 = values[sweepParams['nPoints']-1::,0]
  v2 = values[sweepParams['nPoints']-1::,1]
  
  return (i,v,i2,v2)
