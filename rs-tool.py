#!/usr/bin/env python3
# author: grey@christoforo.net
import ipaddress
import visa # https://github.com/hgrecco/pyvisa
import numpy
import sys
import time

import k2450 # functions to talk to a keithley 2450 sourcemeter
import rs # grey's sheet resistance library

# for plotting
import matplotlib.pyplot as plt
plt.switch_backend("Qt5Agg")

# debugging/testing stuff
#visa.log_to_screen() # for debugging
#import timeit


def main():
  # create a visa resource manager
  rm = visa.ResourceManager('@py') # select pyvisa-py (pure python) backend
  
  # ====for TCPIP comms====
  instrumentIP = ipaddress.ip_address('192.168.1.204') # IP address of sourcemeter
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
  
  # form a connection to our sourcemeter
  sm = k2450.visaConnect(rm, openParams)
  if sm is None:
    exit()

  # generic 2450 setup
  k2450.setup2450(sm)
  
  sweepParams = {} # here we'll store the parameters that define our sweep
  sweepParams['maxCurrent'] = 0.005 # amps
  sweepParams['sweepStart'] = -0.003 # volts
  sweepParams['sweepEnd'] = 0.003 # volts
  # for very unconductive samples
  #sweepParams['maxCurrent'] = 0.00001 # amps
  #sweepParams['sweepStart'] = -15 # volts
  #sweepParams['sweepEnd'] = 15 # volts
  
  sweepParams['nPoints'] = 101
  sweepParams['sourceFun'] = 'voltage'
  sweepParams['senseFun'] = 'current'
  sweepParams['fourWire'] = True
  sweepParams['nplc'] = 1 # intigration time (in number of power line cycles)
  sweepParams['autoZero'] = False
  sweepParams['stepDelay'] = -1 # seconds (-1 for auto, nearly zero, delay)
  sweepParams['durationEstimate'] = k2450.estimateSweepTimeout(sweepParams['nPoints'], sweepParams['stepDelay'], sweepParams['nplc'])
  k2450.configureSweep(sm,sweepParams)
  
  time.sleep(5)
  
  
  # initiate the forward sweep
  k2450.doSweep(sm)
  
  #sm.write(':SOURCE1:VOLTAGE:LEVEL:IMMEDIATE:AMPLITUDE {:}'.format(sweepParams['sweepStart']))
  # get the data
  [i,v] = k2450.fetchSweepData(sm,sweepParams)
  
  fig = plt.figure() # make a figure to put the plot into
  if i is not None:
    ax = fig.add_subplot(2,1,1)
    ax.clear()
    ax.set_title('Forward Sweep Results',loc="right")
    rs.plotSweep(i,v,ax) # plot the sweep results
    plt.show(block=False)
  
  # setup for reverse sweep
  newEnd = sweepParams['sweepStart']
  newStart = sweepParams['sweepEnd']
  sweepParams['sweepStart'] = newStart # volts
  sweepParams['sweepEnd'] = newEnd # volts
  k2450.configureSweep(sm,sweepParams)
  time.sleep(5)
  # initiate the reverse sweep
  k2450.doSweep(sm)
  # get the data
  [i,v] = k2450.fetchSweepData(sm,sweepParams)
  
  if i is not None:
    ax = fig.add_subplot(2,1,2)
    ax.clear()
    ax.set_title('Reverse Sweep Results',loc="right")
    rs.plotSweep(i,v,ax) # plot the sweep results
    plt.show()  
  
  print("Closing connection to", sm._logging_extra['resource_name'],"...")
  sm.close() # close connection
  print("Connection closed.")

if __name__ == "__main__":
  main()
