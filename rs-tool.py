#!/usr/bin/env python3
# author: grey@christoforo.net
import ipaddress
import numpy
import sys
import time
import math

import k2450 # functions to talk to a keithley 2450 sourcemeter
import rs # grey's sheet resistance library

# for plotting
import matplotlib.pyplot as plt
plt.switch_backend("Qt5Agg")

# debugging/testing stuff
#visa.log_to_screen() # for debugging
#import timeit


def main():
  
  # ====for TCPIP comms====
  instrumentIP = ipaddress.ip_address('172.17.3.60')
  #instrumentIP = ipaddress.ip_address('192.168.1.204') # IP address of sourcemeter
  #fullAddress = 'TCPIP::'+str(instrumentIP)+'::INSTR'
  fullAddress = 'TCPIP::'+str(instrumentIP)+'::5025::SOCKET' # for raw TCPIP comms directly through a socket @ port 5025 (probably worse than INSTR)
  deviceTimeout = 1000 # ms
  openParams = {'resource_name': fullAddress, 'timeout': deviceTimeout, '_read_termination': u'\n'}
  
  # ====for serial rs232 comms=====
  #serialPort = "/dev/ttyUSB0"
  #fullAddress = "ASRL"+serialPort+"::INSTR"
  #deviceTimeout = 1000 # ms
  #sm = rm.open_resource(smAddress)
  #sm.set_visa_attribute(visa.constants.VI_ATTR_ASRL_BAUD,57600)
  #sm.set_visa_attribute(visa.constants.VI_ASRL_END_TERMCHAR,u'\r')
  #openParams = {'resource_name':fullAddress, 'timeout': deviceTimeout}
  
  if 'SOCKET' in fullAddress:
    rm = None
  else:
    import visa # https://github.com/hgrecco/pyvisa
    # create a visa resource manager
    rm = visa.ResourceManager('@py') # select pyvisa-py (pure python) backend
  sleepTime = 10 #s  
  
  # form a connection to our sourcemeter
  sm = k2450.visaConnect(rm, openParams)
  if sm is None:
    exit()

  # generic 2450 setup
  k2450.setup2450(sm)
  
  sweepParams = {} # here we'll store the parameters that define our sweep
  #sweepParams['maxCurrent'] = 0.005 # amps
  #sweepParams['sweepStart'] = -0.003 # volts
  #sweepParams['sweepEnd'] = 0.003 # volts
  #0.001 ua
  # for very unconductive samples
  sweepParams['maxCurrent'] = 0.00001 # amps
  sweepParams['sweepStart'] = -1 # volts
  sweepParams['sweepEnd'] = -0.5 # volts
  
  sweepParams['rangeType'] = 'BEST' # fixed, auto or best
  sweepParams['failAbort'] = 'OFF'
  sweepParams['dual'] = 'ON'
  sweepParams['nPoints'] = 21
  sweepParams['sourceFun'] = 'voltage'
  sweepParams['senseFun'] = 'current'
  sweepParams['fourWire'] = True
  sweepParams['nplc'] = 3 # intigration time (in number of power line cycles)
  sweepParams['autoZero'] = True
  sweepParams['stepDelay'] = 2 # ms (-1 for auto, nearly zero, delay)
  #sweepParams['durationEstimate'] = k2450.estimateSweepTimeout(sweepParams['nPoints'], sweepParams['stepDelay'], sweepParams['nplc'])
  
  rOpt = {}
  rOpt['n'] = 5
  rOpt['fourWire'] = True
  rOpt['nplc'] = 10
  rOpt['sourceCurr'] = 1e-10 # amps
  rOpt['vMax'] = 20e-3 # 20e-3, 200e-3, 2, 20 200 volts
  rOpt['vMax'] = 200e-3
  rOpt['vMax'] = 2e-3
  rOpt['vMax'] = 20
  rOpt['vMax'] = 200
  
  rsOpt = {}
  rsOpt['fourWire'] = True
  rsOpt['nplc'] = 10
  rsOpt['iMax'] = 1e-6
  rsOpt['vLim'] = 2
  rsOpt['nPoints'] = 21
  rsOpt['oCom'] = True
  
  r = k2450.measureR(sm,rOpt)
  rS = float(r[4]*math.pi/math.log(2))
  rSString = "R_s= {:0.6g}".format(rS) + u" [\u03A9/\u25AB]"
  print (rSString)  
  
  #k2450.configureSweep(sm,sweepParams)
  
  #time.sleep(sleepTime)
  
  
  # initiate the forward sweep
  #k2450.doSweep(sm)
  
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
  time.sleep(sleepTime)
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
