#!/usr/bin/env python3
# author: grey@christoforo.net

import sys
import ipaddress
import visa # https://github.com/hgrecco/pyvisa
import numpy
from scipy.optimize import curve_fit
from math import pi, log, sqrt

# for the GUI
import pyqtGen
from PyQt5 import QtCore, QtGui, QtWidgets
class MainWindow(QtWidgets.QMainWindow):
  def __init__(self):
    QtWidgets.QMainWindow.__init__(self)
    self.ui = pyqtGen.Ui_MainWindow()
    self.ui.setupUi(self)
    
    self.ui.pushButton.clicked.connect(self.doSweep)
    
    # for now put this here, should be initiated by user later:
    self.createResourceManager()
    
    # ====for TCPIP comms====
    instrumentIP = ipaddress.ip_address('10.42.0.60') # IP address of sourcemeter
    fullAddress = 'TCPIP::'+str(instrumentIP)+'::INSTR'
    timeout = 1000 # ms
    #fullAddress = 'TCPIP::'+smAddressIP+'::5025::SOCKET' # for raw TCPIP comms directly through a socket @ port 5025 (probably worse than INSTR)
    openParams = {'resource_name': fullAddress, 'timeout': timeout, '_read_termination': u'\n'}    
    self.connectToKeithley(openParams)
    
  def createResourceManager(self):
    self.rm = visa.ResourceManager('@py') # select pyvisa-py (pure python) backend
  
  def connectToKeithley(self, openParams):
    self.sm = visaConnect(self.rm, openParams)
    
  def doSweep(self):
    setupSweep(self.sm)

#from pyqtGen import Ui_MainWindow
#class MyWindow(QtGui.QDialog):
#  def __init__(self, parent=None):
#    QtGui.QWidget.__init__(self, parent)
#    self.ui = Ui_Dialog()
#                                    self.ui.setupUi(self)

# for plotting
import matplotlib.pyplot as plt
plt.switch_backend("Qt5Agg")

# debugging/testing stuff
import time
#visa.log_to_screen() # for debugging
#import timeit


def main():
  app = QtWidgets.QApplication(sys.argv)
  sweepUI = MainWindow()
  sweepUI.show()
  print (app.exec_())  

  # create a visa resource manager
  #rm = visa.ResourceManager('@py') # select pyvisa-py (pure python) backend
  
  # ====for TCPIP comms====
  #instrumentIP = ipaddress.ip_address('10.42.0.60') # IP address of sourcemeter
  #fullAddress = 'TCPIP::'+str(instrumentIP)+'::INSTR'
  #timeout = 1000 # ms
  #fullAddress = 'TCPIP::'+smAddressIP+'::5025::SOCKET' # for raw TCPIP comms directly through a socket @ port 5025 (probably worse than INSTR)
  #openParams = {'resource_name': fullAddress, 'timeout': timeout, '_read_termination': u'\n'}
  
  # ====for serial rs232 comms=====
  #serialPort = "/dev/ttyUSB0"
  #fullAddress = "ASRL"+serialPort+"::INSTR"
  #timeout = 1000 # ms
  #sm = rm.open_resource(smAddress)
  #sm.set_visa_attribute(visa.constants.VI_ATTR_ASRL_BAUD,57600)
  #sm.set_visa_attribute(visa.constants.VI_ASRL_END_TERMCHAR,u'\r')
  #openParams = {'resource_name':fullAddress, 'timeout': timeout}
  
  # form a connection to our sourcemeter
  #sm = visaConnect(rm, openParams)

  # setup for sweep
  #setupSweep(sm)
  
  print("Done!")
  sweepUI.sm.close() # close connection
  
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
    return
  
  # setup the sweep
  sm.write(':SOURCE1:SWEEP:VOLTAGE:LINEAR {:}, {:}, {:}, {:}'.format(sweepStart,sweepEnd,nPoints,stepDelay))
  # trigger the reading
  sm.write(':INITIATE:IMMEDIATE') #should be: sm.assert_trigger()
  sm.write('*WAI') # no other commands during this
  
  # ask for the contents of the sweep buffer with appropraite timeout
  # here we assume one measurement takes no longer than 100ms
  # and the initial setup time is 500ms
  # this value might become an issue (not big enough) if averaging or high NPLC is configured  
  if stepDelay is -1: 
    stepDelay = 0
  oldTimeout = sm.timeout
  sm.timeout = 500 + round(nPoints*(stepDelay*1000+100))  
  t = time.time()
  opc = sm.query('*OPC?') # wait for the operation to complete
  elapsed=time.time()-t
  sm.timeout = oldTimeout
  nReadings = int(sm.query(':TRACE:ACTUAL?'))
  print ("Sample frequency =",nReadings/elapsed,"Hz")
  
  if nReadings != nPoints: # check if we got enough readings
    print("Error: We expected", nPoints, "data points, but the Keithley's data buffer contained", nReadings)
    printEventLog(sm)
    return
  
  # ask keithley to return its buffer
  values = sm.query_values ('TRACE:DATA? {:}, {:}, "defbuffer1", SOUR, READ'.format(1,nPoints))

  # process what we got back  
  values = values.reshape([-1,2])
  v = values[:,0]
  i = values[:,1]
  
  # plot it up
  plt.title('Sweep results')
  plt.xlabel('Voltage [V]')
  plt.ylabel('Current [A]')
  plt.plot(v,i,marker='.')
  plt.grid(b=True)
  plt.draw()
  #plt.show()
  
def printEventLog(sm):
  while True:
    errorString = sm.query(':SYSTEM:EVENTLOG:NEXT?')
    errorSplit = errorString.split(',')
    errorNum = int(errorSplit[0])
    if errorNum == 0:
      break # no error
    else:
      print(errorSplit[1])

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
  
  print("Device identified as",idnString)
  
  return d

if __name__ == "__main__":
  main()
