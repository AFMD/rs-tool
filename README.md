# rs-tool
controls Keithley sourcemeter to measure current voltage curves via an in-line four point probe and calculate sheet resistance from them.

Pure Python (and pure open source) implimentation (no National Instruments libraries) via [pyvisa](https://github.com/hgrecco/pyvisa) and [pyvisa-py](https://github.com/hgrecco/pyvisa-py) with Python 3 and QT5 gui.

![User Interface](/ui.png)  
![User Interface2](/plots.png)

## Requirements
Keithley 2450 sourcemeter. Connected via Ethernet/serial/usb. You must know the VISA address, that's something like `TCPIP::192.168.1.204::INSTR` for an Ethernet connected device.

## Installation
How to install on various operating systems.
### Arch Linux
``` bash
pacaur -S --needed git python-pyqt5 python-scipy python-uncertainties python-pyvisa python-pyvisa-py python-matplotlib
git clone git@github.com:AFMD/rs-tool.git
cd rs-tool
pyuic5 userInterface.ui -o pyqtGen.py #build the python/qt5 interface file
./rs-tool-gui.py
```
### Ubuntu
TODO
### MacOS
TODO
### Windows
TODO
