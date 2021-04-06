#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
PiPyADC: Microgrid Demo for ADS1256 and DAC8532 in module pipyad_da:

Edward Springer 2019-03-28
"""
import logging
import os
import sys
import time
import datetime

import argparse
#from elasticsearch import Elasticsearch

from ADS1256_definitions import *
from ad_da import AD_DA

print("Copyright 2021, Battelle Energy Alliance, LLC")

if not os.path.exists("/dev/spidev0.1"):
    raise IOError("Error: No SPI0.1 device found. Check settings in /boot/config.txt")

### START MICROGRID ###
################################################################################
###  STEP 0: CONFIGURE CHANNELS AND USE DEFAULT OPTIONS FROM CONFIG FILE: ###
#
# For channel code values (bitmask) definitions, see ADS1256_definitions.py.
# The values representing the negative and positive input pins connected to
# the ADS1256 hardware multiplexer must be bitwise OR-ed to form eight-bit
# values, which will later be sent to the ADS1256 MUX register. The register
# can be explicitly read and set via ADS1256.mux property, but here we define
# a list of differential channels to be input to the ADS1256.read_sequence()
# method which reads all of them one after another.
#
# ==> Each channel in this context represents a differential pair of physical
# input pins of the ADS1256 input multiplexer.
#
# ==> For single-ended measurements, simply select AINCOM as the negative input.
#
# AINCOM does not have to be connected to AGND (0V), but it is if the jumper
# on the Waveshare board is set.
#
AIN0, AIN1 = POS_AIN0|NEG_AINCOM, POS_AIN1|NEG_AINCOM # AIN0 is Frequency input, AIN1 is SOC
#AIN2 = POS_AIN2|NEG_AINCOM
#AIN3, AIN4, AIN5 = POS_AIN3|NEG_AINCOM, POS_AIN4|NEG_AINCOM, POS_AIN5|NEG_AINCOM

# Specify here an arbitrary length list (tuple) of arbitrary input channel pair
# eight-bit code values to scan sequentially from index 0 to last.
# Eight channels fit on the screen nicely for this example..
CH_SEQUENCE = (AIN0, AIN1)

MAX_CURTAIL     = 5000
MAX_BATT_OUT    = 1000 #Watts 
MAX_BATT_CHARGE = 15000 #KWh
POWER_VAR = 0
POWER_MAX = 1000 #Watts

###############################################################################
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--delay', type=float, default=0, help='Loop Time delay')
    parser.add_argument('-f', '--frequency', type=float, default=0, help='Initial Frequency')
    parser.add_argument('-s', '--soc', type=float, default=50, help='Initial \'State of Charge\'')
    parser.add_argument('-j', '--inertia', type=int, default=0, help='Moment of Inertia to be used')
    parser.add_argument('-t', '--time', type=float, default=0, help='dT to be used')
    parser.add_argument('-e', '--elasticsearch_ip', type=str, help='ElasticSearch IP Address')
    parser.add_argument('-g', '--elasticsearch_port', type=int, help='ElasticSearch Port')
    parser.add_argument('-p', '--proxy_ip', type=str, help='Proxy IP Address')
    parser.add_argument('-r', '--proxy_port', type=int, help='Proxy Port')
    parser.add_argument('-z', '--file', type=str, help='filename')
    return parser.parse_args()

# Format nice looking text output:
def nice_output(v_freq, v_soc, vU, vC, ctrl, curtail, soc, net, freq, final,pwr_bal):
    sys.stdout.write(
          "\0337" # Store cursor position
        + "Pi ---> AB\n"
        + "\tv_freq:\t{: 8.5f}; v_soc:\t{: 8.5f};\n".format(v_freq, v_soc)
    + "AB ---> Pi\n"
        + "\tvU:\t{: 8.5f}; vC:\t{: 8.5f};\n".format(vU, vC)
    + "Computed on Pi\n"
        + "\tctrl:\t{: 8.5f}; curtail:\t{: 8.5f}; \n\tsoc:\t{: 8.5f}; \n\tnet:\t{: 8.5f} \n\tfreq:\t{: 8.5f};\n\tpwr_bal:\t{: 8.5f};\n".format(ctrl, curtail, soc, net, freq, pwr_bal)
    + "loop time:\t{: 8.5f}\n\n".format(final)
        + "\n\033[J\0338" # Restore cursor position etc.
    )

def send_to_elastic(elasticsearch_client, current_time, frequency, state_of_charge, v_freq, v_soc, vU, control, vC, curtail, power_balance, net_change):
    demo = { 'date':convert_time(current_time) }
    demo['frequency'] = frequency
    demo['state_of_charge'] = state_of_charge
    demo['frequency_voltage'] = v_freq
    demo['state_of_charge_voltage'] = v_soc
    demo['u_voltage'] = vU
    demo['c_voltage'] = vC
    demo['control'] = control
    demo['curtail'] = curtail
    demo['power_balance'] = power_balance
    demo['net_change'] = net_change

    elasticsearch_client.index(index='microgrid_demo', doc_type='demo', body=demo)

def convert_time(time_to_convert):
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.localtime(time_to_convert))

def convert_frequency(freq):
    return (((freq - 57.00) * 5) / 6)

def convert_stateOfCharge(soc):
    return ((soc/100) * 5)

def generate_power_balance():
    return 0


def main():
    date_string = ''
    #date_string = '_' + datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S") + '.txt' 
    ctrl    = 0
    freq    = 60    # Initial frequency = 60Hz
    pwr_bal = 0
    Power_Flag = 0
    soc     = 50   # Initial SOC = 50%
    dt      = 1    # Delay for loop
    J       = 40  # moment of inertia of the spinning machines
    delay   = 0
    i       = 0     # Count to link loop values together
    freq_out = 0 # Frequency output to the Gui
    soc_out = 0 # SOC output to Gui

    elasticsearch_ip = "192.168.1.248"
    elasticsearch_port = 9200

    proxy_ip = None
    proxy_port = 0

    ad_da = AD_DA()
    # Quick Calibration to reset ADS1256
    logging.debug("Calibrate ABS1256")
    ad_da.cal_self()

    args = parse_args()
    logging.debug("Parsing input arguments")
    logging.debug("Input arguments: {}".format(args))

    if ad_da.chip_ID != 3:
        print("ERROR: Wrong ID for ADS1256... ID: {}".format(ad_da.chip_ID))
        logging.error("ERROR: Wrong ID for ADS1256... ID: {}".format(ad_da.chip_ID))
        sys.exit(1)

    if args.elasticsearch_ip is not None:
        elasticsearch_ip = args.elasticsearch_ip
    logging.info("ElasticSearch IP Address: {}".format(elasticsearch_ip))

    if args.elasticsearch_port is not None and args.elasticsearch_port > 0:
        elasticsearch_port = args.elasticsearch_port
    logging.info("ElasticSearch Port: {}".format(elasticsearch_port))

    if args.proxy_ip is not None:
        proxy_ip = args.proxy_ip
    logging.info("Proxy IP Address: {}".format(proxy_ip))

    if args.proxy_port is not None and args.proxy_port > 0:
        proxy_port = args.proxy_port
    logging.info("Proxy Port: {}".format(proxy_port))

    if args.delay > 0:
        delay = args.delay
    logging.info("Loop delay: {}".format(delay))

    if args.frequency > 56 and args.frequency < 64:
        freq = args.frequency
    else:
        freq = 60
    logging.info("Initial frequency: {}".format(freq))

    if args.soc >= 0 and args.soc <= 100:
        soc = args.soc
    else:
        soc = 50
    logging.info("Initial \'State Of Charge\': {}".format(soc))

    if args.inertia > 0:
        J = args.inertia
    logging.info("Moment of inertia of the spinning machines: {}".format(J))

    if args.time > 0:
        dt = args.time
    logging.info("Delta time: {}".format(dt))
   
    if args.file is not None: 
        date_string = '_' + args.file + '.txt' 
    else:
        date_string = '_' + datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S") + '.txt' 

    #elasticsearch_client = Elasticsearch([elasticsearch_ip], port=elasticsearch_port)
    count = 3.0
    s_tmp = 0
    v_tmp = 0
    raw_tmp = ad_da.read_sequence(CH_SEQUENCE)
    time.sleep(0.0002)
    while True:
        start = time.time()
        v_freq = convert_frequency(freq) / ad_da.v_mag
        v_soc  = convert_stateOfCharge(soc) / ad_da.v_mag

        if v_freq < 0:
            v_freq = 0
        if v_freq > 5:
            v_freq = 5

        if v_soc < 0:
            v_soc = 0
        if v_soc > 5:
            v_soc = 5
        s_tmp = v_soc
        v_tmp = v_freq

        # Sent frequency and  "state of charge" to AB
        # Channel A is frequency
        # Channel B is SOC
        ad_da.write_dac(ad_da.DAC_CHANNEL_A, ad_da.voltage_convert(v_freq))
        ad_da.write_dac(ad_da.DAC_CHANNEL_B, ad_da.voltage_convert(v_soc))
        time.sleep(0.0002)

        logging.info("Pi ---> AB\t\t[{}] - freq: {}; v_freq: {}; soc: {}; v_soc: {};".format(i, freq, v_freq, soc, v_soc))


        raw_channels = ad_da.read_sequence(CH_SEQUENCE)
        ram_tmp = raw_channels
        voltages     = [i * ad_da.v_per_digit for i in raw_channels]
        delay = 0
        time.sleep(0.0002)

        if count > .02 and count < .09:
        # NOTE: AB was not sending out a vU voltage within the proper range (needed to multiply by 4)
            vU = voltages[1]-count # / ad_da.v_mag
            vC = voltages[0] # / ad_da.v_mag
            count = count + .001

        elif count == 1:
            vU = voltages[1] # / ad_da.v_mag
            vC = voltages[0] # / ad_da.v_mag
            count+=1

        elif count == 3:
            vU = voltages[1] # / ad_da.v_mag
            vC = voltages[0] # / ad_da.v_mag

        logging.info("AB ---> Pi\t\t[{}] - vU: {}; vC: {};".format(i, vU, vC))

        #print("[0] v_freq: {}; v_soc: {}; vU: {}; vC: {}".format(v_freq, v_soc, vU, vC))

        # Convert from voltage to ctrl and curtail
        ctrl = ((vU - 2) / 2) * MAX_BATT_OUT
        curtail = (vC / 4) * MAX_CURTAIL
        
        if Power_Flag > 0:
         pwr_bal = pwr_bal + POWER_VAR
         if pwr_bal > POWER_MAX:
          Power_Flag = 0
        else:
         pwr_bal = pwr_bal - POWER_VAR
         if pwr_bal < -POWER_MAX:
          Power_Flag = 1




        # Use ctrl to update "state of charge"
        # negative ctrl should increase charge in battery
        # positive ctrl should decrease charge in battery
        soc = (soc * MAX_BATT_CHARGE - ctrl) * dt / MAX_BATT_CHARGE

        #print("[1] ctrl: {}; curtail: {};".format(ctrl, curtail))
        #print("[2] soc: {};".format(soc))

        # Make sure that the battery state stays within bounds 0 to 1
        # 0 = 0%
        # 1 = 100%
        if soc < 0:
            ctrl = 0
            soc = 0
        elif soc > 100:
            #ctrl = 0
            soc = 100

        logging.info("Compute on Pi\t\t[{}] - ctrl: {}; curtail: {}; soc: {};".format(i, ctrl, curtail, soc))

        # NOTE: Zero out Curtail for now until AB Logic is updated
        curtail = 0
        # Compute net change
        # Power Balance will be used to add randomness to net change
        # pwr_bal = generate_power_balance()
        net = pwr_bal + ctrl - curtail
        # Compute frequency
        freq = freq + net * dt / (J * freq)
        #print("[3] net: {}; freq: {};\n".format(net, freq))

        logging.info("Compute on Pi\t\t[{}] - net: {}; freq: {};".format(i, net, freq))

        i += 1
        time.sleep(delay)
        end = time.time()

        # Pretty print to console
        nice_output(v_freq, v_soc, vU, vC, ctrl, curtail, soc, net, freq, end-start,pwr_bal)
        file1 = open('/home/pi/Python/output/freq' + date_string,'a')#append mode 
       # file1.write('{topic:"Frequency", payload:')
       # file1.write(str(freq))
       # file1.write('}\n')
        freq_out = round(freq, 2)
        soc_out = round(soc, 2)
        t = round(end-start,4)
        file1.write(str(freq_out)+'\n')
        file1.close()
        file2 = open('/home/pi/Python/output/soc' + date_string,'a')#append mode 
        file2.write(str(soc_out) + '\n') 
        file2.close()
        file3 = open('/home/pi/Python/output/freqraw' + date_string,'a')#append mode 
        file3.write(str(freq) + '\n') 
        file3.close()
        #file2 = open('/home/pi/Python/test.txt','a')#append mode 
        #file2.write(str(ok) + '\n') 
        #file2.close()
        file4 = open('/home/pi/Python/output/loop_time' + date_string, 'a')
        file4.write(str(t)+'\n')
        file4.close()
        
        # Log Pi data to Elasticsearch
        #send_to_elastic(elasticsearch_client, end, freq, soc, v_freq, v_soc, vU, ctrl, vC, curtail, pwr_bal, net)

        if freq > 62 or freq < 58:
            print("ERROR: Microgrid out of phase...")
            logging.error("ERROR: Microgrid out of phase...")
            break



        # Convert to voltage values
        # Make sure to divide by PI specific voltage magnitude
       
# Start microgrid demo
if __name__ == "__main__":
    try:
        logging.basicConfig(filename='microgrid.log', level=logging.WARNING, format="%(asctime)s:%(levelname)s:%(message)s")
        print("\033[2J\033[H") # Clear screen
        #print(__doc__)
        print("\nPress CTRL-C to exit.")
        logging.info("Starting Microgrid demo")
        main()

    except (KeyboardInterrupt):
        logging.warning("User exit...")
        logging.info("Ending Microgrid demo")
        print("\n"*8 + "User exit.\n")
        sys.exit(0)
