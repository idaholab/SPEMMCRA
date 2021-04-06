Introduction
This code provides an implementation of the swing equation to simulate the frequency and voltage of a microgrid. The current implementation supports a battery model which should be run on a raspberry pi or virtual machine. The raspberry pi provides a control and frequency sensor output for a PLC.  A PLC is required evaluate the output form the raspberry pi and apply an actuator. This provides a frequency control loop. This system is useful for providing analog inputs and accepting analog reads from a PLC. The microgrid additionally supports DNP3 and MODBUS communication with a PLC.

Getting Started
The Waveshare AD/DA board and a Raspberry Pi are required to run the analog version of this code. 
Waveshare - https://www.waveshare.com/wiki/High-Precision_AD/DA_Board
Raspberry pi -  https://www.raspberrypi.org/products/raspberry-pi-4-model-b/
Dependencies – Python 3, numpy, waveshare files (included)
Build and Test – the code requires a starting frequency and battery state of charge value
	Python micgrigrid_py.py -s 50 -f 60
DNP3
	DNP3 traffic require the use of OpenPLC. The OpenPLC runtime and editor can be installed using the following instructions.
	https://www.openplcproject.com/getting-started/
Once installed, switch to the development branch and start DNP3 mode as follows:
	git checkout development
	Python microgrid_py.py -s 50 -f 60 -dn

