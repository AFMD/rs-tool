from scipy.optimize import curve_fit
from math import pi, log, sqrt
import uncertainties as eprop # for confidence intervals
import numpy

# for plotting
import matplotlib.pyplot as plt
plt.switch_backend("Qt5Agg")

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
