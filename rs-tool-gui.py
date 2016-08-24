#!/usr/bin/env python3
# author: grey@christoforo.net
import ipaddress
import visa # https://github.com/hgrecco/pyvisa
import numpy
import sys

import k2450 # functions to talk to a keithley 2450 sourcemeter
import rs # grey's sheet resistance library

# for plotting
import matplotlib.pyplot as plt
plt.switch_backend("Qt5Agg")

# debugging/testing stuff
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
    k2450.doSweep(self.mainWindow.sm)
    # get the data
    [i,v] = k2450.fetchSweepData(self.mainWindow.sm,self.mainWindow.sweepParams)
    if i is not None:
      self.mainWindow.ax1.clear()
      self.mainWindow.ax1.set_title('Forward Sweep Results',loc="right")
      rs.plotSweep(i,v,self.mainWindow.ax1) # plot the sweep results

    # now do a reverse sweep
    reverseParams = self.mainWindow.sweepParams.copy()
    reverseParams['sweepStart'] = self.mainWindow.sweepParams['sweepEnd']
    reverseParams['sweepEnd'] = self.mainWindow.sweepParams['sweepStart']
    k2450.configureSweep(self.mainWindow.sm,reverseParams)
    k2450.doSweep(self.mainWindow.sm)
    # get the data
    [i,v] = k2450.fetchSweepData(self.mainWindow.sm,reverseParams)
    if i is not None:
      self.mainWindow.ax2.clear()
      self.mainWindow.ax2.set_title('Reverse Sweep Results',loc="right")
      rs.plotSweep(i,v,self.mainWindow.ax2) # plot the sweep results  
    
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

    k2450.setup2450(self.sm)
    
    self.sweepParams = {} # here we'll store the parameters that define our sweep
    self.sweepParams['maxCurrent'] = 0.05 # amps
    self.sweepParams['sweepStart'] = -0.003 # volts
    self.sweepParams['sweepEnd'] = 0.003 # volts
    self.sweepParams['nPoints'] = 101
    self.sweepParams['stepDelay'] = -1 # seconds (-1 for auto, nearly zero, delay)
    self.sweepParams['durationEstimate'] = k2450.estimateSweepTimeout(self.sweepParams['nPoints'], self.sweepParams['stepDelay'])
    k2450.configureSweep(self.sm,self.sweepParams)
    
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
    self.sm = k2450.visaConnect(self.rm, openParams)
    
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
  app = QtWidgets.QApplication(sys.argv)
  sweepUI = MainWindow()
  sweepUI.show()
  sys.exit(app.exec_())

if __name__ == "__main__":
  main()

