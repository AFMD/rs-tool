#!/usr/bin/env python3
# author: grey@christoforo.net

import sys
import ipaddress
import visa # https://github.com/hgrecco/pyvisa
import numpy
from scipy.optimize import curve_fit
from math import pi, log, sqrt

# for plotting
import matplotlib.pyplot as plt
plt.switch_backend("Qt5Agg")

# debugging/testing stuff
import time
#visa.log_to_screen() # for debugging
#import timeit

# for the GUI
import pyqtGen
from PyQt5 import QtCore, QtGui, QtWidgets
class MainWindow(QtWidgets.QMainWindow):
  def __init__(self):
    QtWidgets.QMainWindow.__init__(self)
    self.ui = pyqtGen.Ui_MainWindow()
    self.ui.setupUi(self)
    
    # for now put these here, should be initiated by user later:
    self.rm = visa.ResourceManager('@py') # select pyvisa-py (pure python) backend
    self.connectToKeithley(openParams)
    self.guiSetupSweep()
    
    # connect up the sweep button
    self.ui.pushButton.clicked.connect(self.doSweep)
    
  def __del__(self):
    try:
      print("Closing connection to", self.sm._logging_extra['resource_name'],"...")
      self.sm.close() # close connection
      print("Connection closed.")
    except:
      return
    
  def connectToKeithley(self, openParams):
    self.sm = visaConnect(self.rm, openParams)
    
  def guiSetupSweep(self):
    self.sweepParams = setupSweep(self.sm)
    
  def doSweep(self):
    self.ui.pushButton.setDisabled(True) #TODO: somehow this is broken
    time.sleep(1)
    # initiate the sweep
    doSweep(self.sm)
    # get the data
    [i,v] = fetchSweepData(self.sm,self.sweepParams)
    # plot the sweep results
    plotSweep(i,v)
    self.ui.pushButton.setEnabled(True) #TODO: somehow this is broken


# some global variables defining how we'll talk to the instrument
# ====for TCPIP comms====
instrumentIP = ipaddress.ip_address('10.42.0.60') # IP address of sourcemeter
fullAddress = 'TCPIP::'+str(instrumentIP)+'::INSTR'
deviceTimeout = 1000 # ms
#fullAddress = 'TCPIP::'+str(instrumentIP)+'::5025::SOCKET' # for raw TCPIP comms directly through a socket @ port 5025 (probably worse than INSTR)
openParams = {'resource_name': fullAddress, 'timeout': deviceTimeout, '_read_termination': u'\n'}

# ====for serial rs232 comms=====
#serialPort = "/dev/ttyUSB0"
#fullAddress = "ASRL"+serialPort+"::INSTR"
#deviceTimeout = 1000 # ms
#sm = rm.open_resource(smAddress)
#sm.set_visa_attribute(visa.constants.VI_ATTR_ASRL_BAUD,57600)
#sm.set_visa_attribute(visa.constants.VI_ASRL_END_TERMCHAR,u'\r')
#openParams = {'resource_name':fullAddress, 'timeout': deviceTimeout}


def main():
  
  # ==== uncomment this for GUI ====
  #app = QtWidgets.QApplication(sys.argv)
  #sweepUI = MainWindow()
  #sweepUI.show()
  #sys.exit(app.exec_())
  # ==== end gui ====

  # create a visa resource manager
  rm = visa.ResourceManager('@py') # select pyvisa-py (pure python) backend
  
  # form a connection to our sourcemeter
  sm = visaConnect(rm, openParams)
  if sm is None:
    exit()

  # setup for sweep
  sweepParams = setupSweep(sm)
  
  # initiate the sweep
  doSweep(sm)
  
  # get the data
  [i,v] = fetchSweepData(sm,sweepParams)
  
  # plot the sweep results
  plotSweep(i,v)
  
  print("Closing connection to", sm._logging_extra['resource_name'],"...")
  sm.close() # close connection
  print("Connection closed.")
  
def setupSweep(sm):
  maxCurrent = 0.05 # amps
  sweepStart = -0.003 #volts
  sweepEnd = 0.003 # volts
  nPoints = 101
  stepDelay = -1 # seconds (-1 for auto, nearly zero, delay)
  sm.write("*RST")
  sm.write(":TRACE:CLEAR") # clear the defualt buffer ("defbuffer1")
  sm.write("*CLS") # clear status & system logs and associated registers
  sm.write("*SRE {:}".format((1<<2) + (1<<4))) # enable error reporting via status bit (by setting EAV bit)
  sm.write("*LANG SCPI")
  
  # setup for binary (superfast) data transfer
  sm.write(":FORMAT:DATA REAL")
  sm.values_format.container = numpy.array
  sm.values_format.datatype = 'd'
  
  sm.write(':SOURCE1:FUNCTION VOLTAGE')
  sm.write(':SOURCE1:VOLTAGE:RANGE {:}'.format(max(map(abs,[sweepStart,sweepEnd]))))
  sm.write(':SOURCE1:VOLTAGE:ILIMIT {:}'.format(maxCurrent))
  sm.write(':SENSE1:FUNCTION "CURRENT"')
  sm.write(':SENSE1:CURRENT:RANGE {:}'.format(maxCurrent))
  sm.write(':SENSE1:CURRENT:RSENSE ON') # rsense (remote sense) ON means four wire mode
  sm.write(':ROUTE:TERMINALS FRONT')
  sm.write(':SOURCE1:VOLTAGE:LEVEL:IMMEDIATE:AMPLITUDE {:}'.format(sweepStart)) # set output to sweep start voltage
  
  # do one auto zero manually (could take over a second)
  oldTimeout = sm.timeout
  sm.timeout = 5000  
  sm.write(':SENSE1:AZERO:ONCE') # do one autozero now
  sm.write('*WAI') # no other commands during this
  opc = sm.query('*OPC?') # wait for the operation to complete
  sm.timeout=oldTimeout  
  
  # here are a few settings that trade accuracy for speed
  #sm.write(':SENSE1:CURRENT:AZERO:STATE 0') # disable autozero for future readings
  #sm.write(':SENSE1:CURRENT:NPLC 0.01') # set NPLC
  #sm.write(':SOURCE1:VOLTAGE:READ:BACK OFF') # disable voltage readback
  
  # turn on the source and wait for it to settle
  sm.write(':OUTPUT1:STATE ON')
  sm.write('*WAI') # no other commands during this
  opc = sm.query('*OPC?') # wait for the operation to complete
  
  stb = sm.query('*STB?') # ask for the status byte
  if stb is not '0':
    print ("Error: Non-zero status byte:", stb)
    printEventLog(sm)
    return None
  
  # setup the sweep
  sm.write(':SOURCE1:SWEEP:VOLTAGE:LINEAR {:}, {:}, {:}, {:}'.format(sweepStart,sweepEnd,nPoints,stepDelay))

  # here we assume one measurement takes no longer than 100ms
  # and the initial setup time is 500ms
  # this value might become an issue (not big enough) if averaging or high NPLC is configured    
  if stepDelay is -1:
    stepDelay = 0
  durationEstimate = 500 + round(nPoints*(stepDelay*1000+100))
  
  sweepParams = {'durationEstimate':durationEstimate, 'nPoints':nPoints, }
  
  return sweepParams

def doSweep(sm):
  # check that things are cool before we do the sweep
  stb = sm.query('*STB?') # ask for the status byte
  if stb is not '0':
    print ("Error: Non-zero status byte:", stb)
    printEventLog(sm)
    return  
  
  print ("Sweep initiated...")
  # trigger the swqqqp
  sm.write(':INITIATE:IMMEDIATE') #should be: sm.assert_trigger()
  sm.write('*WAI') # no other commands during this

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
  print ("Sample frequency =",nReadings/elapsed,"Hz")
  print ("Sweep event Log:")
  printEventLog(sm)
  
  if nReadings != sweepParams['nPoints']: # check if we got enough readings
    print("Error: We expected", sweepParams['nPoints'], "data points, but the Keithley's data buffer contained", nReadings)
    return
  
  # ask keithley to return its buffer
  values = sm.query_values ('TRACE:DATA? {:}, {:}, "defbuffer1", SOUR, READ'.format(1,sweepParams['nPoints']))

  # reformat what we got back  
  values = values.reshape([-1,2])
  v = values[:,0]
  i = values[:,1]
  
  return (i,v)

def aLine(x,m,b):
  return m*x + b  

def plotSweep(i,v):
  print("Drawing sweep plot")
  
  # fit the data to a line
  popt, pcov = curve_fit(aLine, v, i)
  slope = popt[0]
  yIntercept = popt[1]
  iFit = aLine(v,slope,yIntercept)
  
  # calculate the errors
  pstd = numpy.sqrt(numpy.diag(pcov)) #standard deviation of estimates
  rInv = slope
  rInvErr = pstd[0] #standard deviation on slope
  R = 1/rInv
  rErr = rInvErr
  rS = R*pi/log(2)
  rSErr = rErr*pi/log(2)

  rString = u"R={0:.1f}\u00B1{1:.1f} [\u03A9]".format(R, rErr)
  print (rString)
  rSString = u"R_s={0:.1f}\u00B1{1:.1f} [\u03A9/\u25AB]".format(rS, rSErr)
  print (rSString)
  rSStringShort = "{0:.1f}+/-{1:.1f}".format(rS, rSErr)

  
  # draw the plot
  plt.title('Sweep results')
  plt.xlabel('Voltage [V]')
  plt.ylabel('Current [A]')
  data, = plt.plot(v,i,'ro', label="I-V data points")
  fit, = plt.plot(v,iFit, label="Best linear fit")  
  fit.axes.text(0.1,0.9,'$'+rString+'$', transform = fit.axes.transAxes)
  fit.axes.text(0.1,0.8,'$'+rSString+'$', transform = fit.axes.transAxes)
  plt.legend(handles=[data, fit],loc=4)
  plt.grid(b=True)
  plt.draw()
  plt.show()
  
def printEventLog(sm):
  while True:
    errorString = sm.query(':SYSTEM:EVENTLOG:NEXT?')
    errorSplit = errorString.split(',')
    errorNum = int(errorSplit[0])
    if errorNum == 0:
      break # no error
    else:
      errorSubSplit = errorSplit[1][1:-1] # toss quotations
      errorSubSplit = errorSubSplit.split(';')
      print(errorSubSplit[2], errorSubSplit[0],"TYPE",errorSubSplit[1],)
  sm.write(':SYSTEM:CLEAR') # clear the logs since we've read them now

# connects to a instrument/device given a resource manager and some open parameters
def visaConnect (rm, openParams):
  print("Connecting to", fullAddress, "...")
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

if __name__ == "__main__":
  main()
