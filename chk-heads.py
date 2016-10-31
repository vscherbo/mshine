#!/usr/bin/python -t
# -*- coding: utf-8 -*-

from __future__ import print_function
import heads_sensor
import sys
import RPIO
import signal
import time

def signal_handler(signal, frame):
    global loop_flag
    loop_flag = False

signal.signal(signal.SIGINT, signal_handler)

alarm_limit = 1

def do_nothing():
    pass

def heads_started(gpio_id, value):
    global hs
    hs.ignore_start()
    hs.watch_stop(heads_finished),
    print("Стартовали головы", "gpio_id="+str(gpio_id)+ ", value="+str(value))

def heads_finished(gpio_id, value):
    global hs
    hs.ignore_stop()
    print("Закончились головы", "gpio_id="+str(gpio_id)+ ", value="+str(value))



hs = heads_sensor.Heads_sensor(gpio_heads_start = 25, gpio_heads_stop = 14, timeout = 2000)
hs.watch_start(heads_started),

step_max = 2

loop_flag = True
step_counter = 0
while loop_flag:
    step_counter += 1
    print(step_counter)
    time.sleep(1)

RPIO.cleanup()
print("Exiting")
sys.exit(0)
