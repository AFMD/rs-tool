#!/usr/bin/env python3
# author: grey@christoforo.net
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

#========= start print override stuff =========
# this stuff is for overriding print() so that
# any calls to it are mirrored to my gui's log pane 
import builtins as __builtin__
systemPrint = __builtin__.print
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
    systemPrint(*args, **kwargs) # print to our string buffer
    myPrinter.writeToLog.emit(stringBuf.getvalue()) # send the print to the gui
    myPrinter.scrollLog.emit() # tell the gui to scroll the log
    stringBuf.close()
    kwargs['file'] = sys.stdout
  return systemPrint(*args, **kwargs) # now do the print for real
__builtin__.print = print
#========= end print override stuff =========

# this is the thread where the sweep takes place
class sweepThread(QtCore.QThread):
  def __init__(self, mainWindow, parent=None):
    QtCore.QThread.__init__(self, parent)
    self.mainWindow = mainWindow

  def run(self):
    self.mainWindow.ui.applyButton.setEnabled(False)
    self.mainWindow.ui.sweepButton.setEnabled(False)
    if not k2450.doSweep(self.mainWindow.sm):
      print ("Failed to do forward sweep.")
    else:
      # get the forward data
      [i,v] = k2450.fetchSweepData(self.mainWindow.sm,self.mainWindow.sweepParams)
      self.mainWindow.ax1.clear()
      if i is not None:
        self.mainWindow.ax1.set_title('Forward Sweep Results',loc="right")
        rs.plotSweep(i,v,self.mainWindow.ax1) # plot the sweep results
      else:
        print("Failed to fetch forward sweep data.")

    # now do a reverse sweep
    reverseParams = self.mainWindow.sweepParams.copy()
    reverseParams['sweepStart'] = self.mainWindow.sweepParams['sweepEnd']
    reverseParams['sweepEnd'] = self.mainWindow.sweepParams['sweepStart']
    if not k2450.configureSweep(self.mainWindow.sm,reverseParams):
      print ("Failed to configure reverse sweep.")
    elif not k2450.doSweep(self.mainWindow.sm):
      print ("Failed to do reverse sweep.")
    else:
      # get the reverse data
      [i,v] = k2450.fetchSweepData(self.mainWindow.sm,reverseParams)
      self.mainWindow.ax2.clear()
      if i is not None:
        self.mainWindow.ax2.set_title('Reverse Sweep Results',loc="right")
        rs.plotSweep(i,v,self.mainWindow.ax2) # plot the sweep results
      else:
        print("Failed to fetch reverse sweep data.")
    print('======================================')
    self.mainWindow.ui.applyButton.setEnabled(True)
    self.mainWindow.ui.sweepButton.setEnabled(True)    
    
class MainWindow(QtWidgets.QMainWindow):
  def __init__(self):
    QtWidgets.QMainWindow.__init__(self)
    
    self.setup = False # to keep track of if the sourcemeter is setup or not
    self.configured = False # to keep track of if the sweep is configured or not
    
    # Set up the user interface from Designer
    self.ui = pyqtGen.Ui_MainWindow()
    self.ui.setupUi(self)
    
    #recall settings
    self.settings = QtCore.QSettings("greyltc", "rs-tool-gui")
    if self.settings.contains('visaAddress'):
      self.ui.visaAddressLineEdit.setText(self.settings.value('visaAddress'))
    if self.settings.contains('readTermination'):
      self.ui.terminationLineEdit.setText(self.settings.value('readTermination'))
    if self.settings.contains('timeout'):
      self.ui.timeoutSpinBox.setValue(int(self.settings.value('timeout')))
    if self.settings.contains('startVoltage'):
      self.ui.startVoltageDoubleSpinBox.setValue(float(self.settings.value('startVoltage')))
    if self.settings.contains('endVoltage'):
      self.ui.endVoltageDoubleSpinBox.setValue(float(self.settings.value('endVoltage')))
    if self.settings.contains('numberOfSteps'):
      self.ui.numberOfStepsSpinBox.setValue(int(self.settings.value('numberOfSteps')))
    if self.settings.contains('currentLimit'):
      self.ui.currentLimitDoubleSpinBox.setValue(float(self.settings.value('currentLimit')))
    if self.settings.contains('stepDelay'):
      self.ui.stepDelayDoubleSpinBox.setValue(float(self.settings.value('stepDelay')))
    if self.settings.contains('autoDelay'):
      self.ui.autoDelayCheckBox.setChecked(self.settings.value('autoDelay') == 'true')
      self.ui.stepDelayDoubleSpinBox.setEnabled(not self.ui.autoDelayCheckBox.isChecked())
    
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
    
    # connect up the sweep button
    self.ui.sweepButton.clicked.connect(self.doSweep)

    # connect up the connect button
    self.ui.connectButton.clicked.connect(self.connectToKeithley)
    
    # connect up the apply button
    self.ui.applyButton.clicked.connect(self.applySweepValues)
    
    # save any changes the user makes
    self.ui.visaAddressLineEdit.editingFinished.connect(lambda: self.settings.setValue('visaAddress',self.ui.visaAddressLineEdit.text()))
    self.ui.terminationLineEdit.editingFinished.connect(lambda: self.settings.setValue('termination',self.ui.terminationLineEdit.text()))
    self.ui.timeoutSpinBox.valueChanged.connect(lambda: self.settings.setValue('timeout',self.ui.timeoutSpinBox.value()))
    
    self.ui.startVoltageDoubleSpinBox.valueChanged.connect(lambda: self.settings.setValue('startVoltage',self.ui.startVoltageDoubleSpinBox.value()))
    self.ui.endVoltageDoubleSpinBox.valueChanged.connect(lambda: self.settings.setValue('endVoltage',self.ui.endVoltageDoubleSpinBox.value()))
    self.ui.numberOfStepsSpinBox.valueChanged.connect(lambda: self.settings.setValue('numberOfSteps',self.ui.numberOfStepsSpinBox.value()))
    self.ui.currentLimitDoubleSpinBox.valueChanged.connect(lambda: self.settings.setValue('currentLimit',self.ui.currentLimitDoubleSpinBox.value()))
    self.ui.stepDelayDoubleSpinBox.valueChanged.connect(lambda: self.settings.setValue('stepDelay',self.ui.stepDelayDoubleSpinBox.value()))
    self.ui.autoDelayCheckBox.stateChanged.connect(self.autoDelayStateChange)
    self.sweepThread = sweepThread(self)    
    
  def __del__(self):
    try:
      print("Closing connection to", self.sm._logging_extra['resource_name'],"...")
      self.sm.close() # close connection
      print("Connection closed.")
    except:
      return
    
  def autoDelayStateChange(self):
    isChecked = self.ui.autoDelayCheckBox.isChecked()
    self.settings.setValue('autoDelay',isChecked)
    self.ui.stepDelayDoubleSpinBox.setEnabled(not isChecked)
  
  def applySweepValues(self):
    #TODO: somehow detect that a user has changed a sweep parameter in the UI and they need to be resent to the sourcemeter
    if not self.setup:
      print("The sourcemeter has not been set up. We'll try that now.")
      self.connectToKeithley()
    if self.setup:
      self.sweepParams = {} # here we'll store the parameters that define our sweep
      #self.sweepParams['maxCurrent'] = 0.05 # amps
      #self.sweepParams['sweepStart'] = -0.003 # volts
      #self.sweepParams['sweepEnd'] = 0.003 # volts
      #self.sweepParams['nPoints'] = 101
      #self.sweepParams['stepDelay'] = -1 # seconds (-1 for auto, nearly zero, delay)
      self.sweepParams['maxCurrent'] = self.ui.currentLimitDoubleSpinBox.value()/1000 # amps
      self.sweepParams['sweepStart'] = self.ui.startVoltageDoubleSpinBox.value()/1000 # volts
      self.sweepParams['sweepEnd'] = self.ui.endVoltageDoubleSpinBox.value()/1000 # volts
      self.sweepParams['nPoints'] = self.ui.numberOfStepsSpinBox.value()
      self.sweepParams['stepDelay'] = self.ui.stepDelayDoubleSpinBox.value()/1000
      if self.ui.autoDelayCheckBox.isChecked():
        self.sweepParams['stepDelay'] = -1 # seconds (-1 for auto, nearly zero, delay)
      self.sweepParams['durationEstimate'] = k2450.estimateSweepTimeout(self.sweepParams['nPoints'], self.sweepParams['stepDelay'])      
      self.configured = k2450.configureSweep(self.sm,self.sweepParams)
      if self.configured:
        print('Sweep parameters applied.')
      else:
        print('Sweep parameters not applied.')
    
  def connectToKeithley(self):
    # ====for TCPIP comms====
    #instrumentIP = ipaddress.ip_address('10.42.0.60') # IP address of sourcemeter
    #fullAddress = 'TCPIP::'+str(instrumentIP)+'::INSTR'
    #deviceTimeout = 1000 # ms
    #fullAddress = 'TCPIP::'+str(instrumentIP)+'::5025::SOCKET' # for raw TCPIP comms directly through a socket @ port 5025 (probably worse than INSTR)
    #openParams = {'resource_name':fullAddress, 'timeout': deviceTimeout}  
    
    # ====for serial rs232 comms=====
    #serialPort = "/dev/ttyUSB0"
    #fullAddress = "ASRL"+serialPort+"::INSTR"
    #deviceTimeout = 1000 # ms
    #sm = rm.open_resource(smAddress)
    #sm.set_visa_attribute(visa.constants.VI_ATTR_ASRL_BAUD,57600)
    #sm.set_visa_attribute(visa.constants.VI_ASRL_END_TERMCHAR,u'\r')
    #openParams = {'resource_name':fullAddress, 'timeout': deviceTimeout}
    if (not self.setup):
      self.openParams = {'resource_name': self.ui.visaAddressLineEdit.text(), 'timeout': self.ui.timeoutSpinBox.value(), '_read_termination': self.ui.terminationLineEdit.text().replace("\\n", '\n').replace("\\t",
  '\t').replace("\\r",'\r')}
      self.sm = k2450.visaConnect(self.rm, self.openParams)
      if self.sm is not None:
        result = k2450.setup2450(self.sm)
        if result is True:
          self.setup = True
    else:
      print('Already connected.')
    
  def scrollLog(self): # scrolls log to maximum position
    self.ui.textBrowser.verticalScrollBar().setValue(self.ui.textBrowser.verticalScrollBar().maximum())    
    
  def doSweep(self):
    if not self.configured:
      print("The sweep has not been configured. We'll try that now.")
      self.applySweepValues()
    if self.configured:
      self.sweepThread.start() 
    #self.ui.tehTabs.setCurrentIndex(0) # switch to plot tab

def main():
  app = QtWidgets.QApplication(sys.argv)
  sweepUI = MainWindow()
  sweepUI.show()
  sys.exit(app.exec_())

if __name__ == "__main__":
  main()

