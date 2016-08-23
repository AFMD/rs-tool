#!/usr/bin/env python3
# author: grey@christoforo.net

import sys
import ipaddress
import visa # https://github.com/hgrecco/pyvisa
import numpy
from scipy.optimize import curve_fit
from math import pi, log, sqrt
import uncertainties as eprop # for confidence intervals

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
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

# for print() overloading for the gui's log pane
import builtins as __builtin__
myPrinter = None
import io
class MyPrinter(QtCore.QObject): # a class that holds the signals we'll need for passing around the log data
  writeToLog = QtCore.pyqtSignal(str) # this signal sends the contents for the log
  scrollLog = QtCore.pyqtSignal() # this signal tells the log to scroll to its max position
def print(*args, **kwargs): # overload the print() function
  global myPrinter
  if myPrinter is not None: # check to see if the gui has created myPrinter
    stringBuf = io.StringIO()
    kwargs['file'] = stringBuf
    __builtin__.print(*args, **kwargs) # print to our string buffer
    myPrinter.writeToLog.emit(stringBuf.getvalue())
    myPrinter.scrollLog.emit()
    stringBuf.close()
    kwargs['file'] = sys.stdout
  return __builtin__.print(*args, **kwargs) # now do the print for rel

# this is the thread where the sweep takes place
class sweepThread(QtCore.QThread):
  def __init__(self, mainWindow, parent=None):
    QtCore.QThread.__init__(self, parent)
    self.mainWindow = mainWindow

  def run(self):
    doSweep(self.mainWindow.sm)
    # get the data
    [i,v] = fetchSweepData(self.mainWindow.sm,self.mainWindow.sweepParams)
    if i is not None:
      self.mainWindow.ax1.clear()
      self.mainWindow.ax1.set_title('Forward Sweep Results',loc="right")
      plotSweep(i,v,self.mainWindow.ax1) # plot the sweep results

    # now do a reverse sweep
    reverseParams = self.mainWindow.sweepParams.copy()
    reverseParams['sweepStart'] = self.mainWindow.sweepParams['sweepEnd']
    reverseParams['sweepEnd'] = self.mainWindow.sweepParams['sweepStart']
    configureSweep2450(self.mainWindow.sm,reverseParams)
    doSweep(self.mainWindow.sm)
    # get the data
    [i,v] = fetchSweepData(self.mainWindow.sm,reverseParams)
    if i is not None:
      self.mainWindow.ax2.clear()
      self.mainWindow.ax2.set_title('Reverse Sweep Results',loc="right")
      plotSweep(i,v,self.mainWindow.ax2) # plot the sweep results  
    

class MainWindow(QtWidgets.QMainWindow):
  def __init__(self):
    QtWidgets.QMainWindow.__init__(self)
    self.ui = pyqtGen.Ui_MainWindow()
    self.ui.setupUi(self)
    
    # tell the UI where to draw put matplotlib plots
    fig = plt.figure(facecolor="white")
    self.ax1 = fig.add_subplot(2,1,1)
    self.ax2 = fig.add_subplot(2,1,2)
    vBox = QtWidgets.QVBoxLayout()
    vBox.addWidget(FigureCanvas(fig))
    self.ui.plotTab.setLayout(vBox)
    
    # set up things for our log pane
    global myPrinter
    myPrinter = MyPrinter()
    myPrinter.writeToLog.connect(self.ui.textBrowser.insertPlainText)
    myPrinter.scrollLog.connect(self.scrollLog)
    self.ui.textBrowser.setTextBackgroundColor(QtGui.QColor('black'))
    self.ui.textBrowser.setTextColor(QtGui.QColor(0, 255, 0))
    #self.ui.textBrowser.setFontWeight(QtGui.QFont.Bold)
    self.ui.textBrowser.setAutoFillBackground(True)
    p = self.ui.textBrowser.palette()
    p.setBrush(9, QtGui.QColor('black'))
    #p.setColor(self.ui.textBrowser.backgroundRole, QtGui.QColor('black'))
    self.ui.textBrowser.setPalette(p)
    
    # for now put these here, should be initiated by user later:
    self.rm = visa.ResourceManager('@py') # select pyvisa-py (pure python) backend
    self.connectToKeithley(openParams)
    if self.sm is None:
      exit()

    setup2450(self.sm)
    
    self.sweepParams = {} # here we'll store the parameters that define our sweep
    self.sweepParams['maxCurrent'] = 0.05 # amps
    self.sweepParams['sweepStart'] = -0.003 # volts
    self.sweepParams['sweepEnd'] = 0.003 # volts
    self.sweepParams['nPoints'] = 101
    self.sweepParams['stepDelay'] = -1 # seconds (-1 for auto, nearly zero, delay)
    self.sweepParams['durationEstimate'] = estimateSweepTimeout2450(self.sweepParams['nPoints'], self.sweepParams['stepDelay'])
    configureSweep2450(self.sm,self.sweepParams)
    
    # connect up the sweep button
    self.ui.pushButton.clicked.connect(self.doSweep)
    
    self.sweepThread = sweepThread(self)    
    
  def __del__(self):
    try:
      print("Closing connection to", self.sm._logging_extra['resource_name'],"...")
      self.sm.close() # close connection
      print("Connection closed.")
    except:
      return
    
  def connectToKeithley(self, openParams):
    self.sm = visaConnect(self.rm, openParams)
    
  def scrollLog(self): # scrolls log to maximum position
    self.ui.textBrowser.verticalScrollBar().setValue(self.ui.textBrowser.verticalScrollBar().maximum())    
    
  def doSweep(self):
    self.ui.tehTabs.setCurrentIndex(0) # switch to plot tab
    self.sweepThread.start()

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
  app = QtWidgets.QApplication(sys.argv)
  sweepUI = MainWindow()
  sweepUI.show()
  sys.exit(app.exec_())
  # ==== end gui ====

  # create a visa resource manager
  rm = visa.ResourceManager('@py') # select pyvisa-py (pure python) backend
  
  # form a connection to our sourcemeter
  sm = visaConnect(rm, openParams)
  if sm is None:
    exit()

  # generic 2450 setup
  setup2450(sm)
  
  sweepParams = {} # here we'll store the parameters that define our sweep
  sweepParams['maxCurrent'] = 0.05 # amps
  sweepParams['sweepStart'] = -0.003 # volts
  sweepParams['sweepEnd'] = 0.003 # volts
  sweepParams['nPoints'] = 101
  sweepParams['stepDelay'] = -1 # seconds (-1 for auto, nearly zero, delay)
  sweepParams['durationEstimate'] = estimateSweepTimeout2450(sweepParams['nPoints'], sweepParams['stepDelay'])
  configureSweep2450(sm,sweepParams)
  
  # initiate the forward sweep
  doSweep(sm)
  # get the data
  [i,v] = fetchSweepData(sm,sweepParams)
  
  fig = plt.figure() # make a figure to put the plot into
  if i is not None:
    ax = fig.add_subplot(2,1,1)
    ax.clear()
    ax.set_title('Forward Sweep Results')
    plotSweep(i,v,ax) # plot the sweep results
    plt.show(block=False)
  
  # setup for reverse sweep
  sweepParams['sweepStart'] = 0.003 # volts
  sweepParams['sweepEnd'] = -0.003 # volts
  configureSweep2450(sm,sweepParams)
  # initiate the reverse sweep
  doSweep(sm)
  # get the data
  [i,v] = fetchSweepData(sm,sweepParams)
  
  if i is not None:
    ax = fig.add_subplot(2,1,2)
    ax.clear()
    ax.set_title('Reverse Sweep Results')
    plotSweep(i,v,ax) # plot the sweep results
    plt.show()  
  
  print("Closing connection to", sm._logging_extra['resource_name'],"...")
  sm.close() # close connection
  print("Connection closed.")
  
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

# returns number of milliseconds to use for the sweep timeout value
def estimateSweepTimeout2450(nPoints,stepDelay):
  # let's estimate how long the sweep will take so we know when to time out
  # here we assume one measurement takes no longer than 100ms
  # and the initial setup time is 500ms
  # this will break if NPLC and averaging are not their default values
  # TODO: take into account NPLC and averaging to make a better estimate
  if stepDelay is -1:
    localStepDelay = 0
  else:
    localStepDelay = stepDelay
  return 500 + round(nPoints*(localStepDelay*1000+100))
  
# setup 2450 for sweep
def configureSweep2450(sm,sweepParams):
  sm.write(':SOURCE1:FUNCTION VOLTAGE')
  sm.write(':SOURCE1:VOLTAGE:RANGE {:}'.format(max(map(abs,[sweepParams['sweepStart'],sweepParams['sweepEnd']]))))
  sm.write(':SOURCE1:VOLTAGE:ILIMIT {:}'.format(sweepParams['maxCurrent']))
  sm.write(':SENSE1:FUNCTION "CURRENT"')
  sm.write(':SENSE1:CURRENT:RANGE {:}'.format(sweepParams['maxCurrent']))
  sm.write(':SENSE1:CURRENT:RSENSE ON') # rsense (remote sense) ON means four wire mode
  sm.write(':ROUTE:TERMINALS FRONT')
  sm.write(':SOURCE1:VOLTAGE:LEVEL:IMMEDIATE:AMPLITUDE {:}'.format(sweepParams['sweepStart'])) # set output to sweep start voltage
  
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
  sm.write(':SOURCE1:SWEEP:VOLTAGE:LINEAR {:}, {:}, {:}, {:}'.format(sweepParams['sweepStart'],sweepParams['sweepEnd'],sweepParams['nPoints'],sweepParams['stepDelay']))

def doSweep(sm):
  # check that things are cool before we do the sweep
  stb = sm.query('*STB?') # ask for the status byte
  if stb is not '0':
    print ("Error: Non-zero status byte:", stb)
    printEventLog(sm)
    return  
  
  print ("Sweep initiated...")
  # trigger the sweep
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
  print ("Sample frequency = {:.1f} Hz".format(nReadings/elapsed))
  print ("Sweep event Log:")
  printEventLog(sm)
  
  if nReadings != sweepParams['nPoints']: # check if we got enough readings
    print("Error: We expected", sweepParams['nPoints'], "data points, but the Keithley's data buffer contained", nReadings)
    return (None,None)
  
  # ask keithley to return its buffer
  values = sm.query_values ('TRACE:DATA? {:}, {:}, "defbuffer1", SOUR, READ'.format(1,sweepParams['nPoints']))

  # reformat what we got back  
  values = values.reshape([-1,2])
  v = values[:,0]
  i = values[:,1]
  
  return (i,v)

def aLine(x,m,b):
  return m*x + b

def plotSweep(i,v,ax):
  print("Drawing sweep plot now")
  
  # fit the data to a line
  popt, fitCovariance = curve_fit(aLine, v, i)
  slope = popt[0]
  yIntercept = popt[1]
  iFit = aLine(v,slope,yIntercept)
  
  slopeSigma = numpy.sqrt(numpy.diag(fitCovariance))[0]
  
  uSlope = eprop.ufloat(slope,slopeSigma)

  R = 1/uSlope # resistance
  rS = R*pi/log(2) # sheet resistance

  rString = "R=" +  R.format('0.6g') + u" [\u03A9]"
  print (rString)
  rSString = "R_s=" + rS.format('0.6g') + u" [\u03A9/\u25AB]"
  print (rSString)
  
  vMax = max(v)
  vMin = min(v)
  vRange = vMax - vMin
  onePercent = 0.01*vRange

  # draw the plot on the given axis
  ax.set_xlabel('Voltage [V]')
  ax.set_ylabel('Current [A]')
  data, = ax.plot(v,i,'ro', label="I-V data points")
  fit, = ax.plot(v,iFit, label="Best linear fit")
  fit.axes.text(0.1,0.9,'$'+rString+'$', transform = fit.axes.transAxes)
  fit.axes.text(0.1,0.8,'$'+rSString+'$', transform = fit.axes.transAxes)
  ax.legend(handles=[data, fit],loc=4)
  ax.set_xlim([vMin-onePercent,vMax+onePercent])
  ax.grid(b=True)
  ax.get_figure().canvas.draw()
  
def printEventLog(sm):
  while True:
    errorString = sm.query(':SYSTEM:EVENTLOG:NEXT?')
    errorSplit = errorString.split('"')
    errorNum = int(errorSplit[0].split(',')[0])
    if errorNum == 0:
      break # no error
    else:
      errorSubSplit = errorSplit[1] # toss quotations
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
