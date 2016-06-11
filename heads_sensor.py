#!/usr/bin/env python
# -*- coding: utf-8 -*-

import RPIO
import time

class Heads_sensor:
    def __init__(self, gpio_heads_start, gpio_heads_stop):
        self.gpio_heads_start = gpio_heads_start
        RPIO.setup(self.gpio_heads_start, RPIO.IN, pull_up_down=RPIO.PUD_DOWN)
        self.gpio_heads_stop = gpio_heads_stop
        RPIO.setup(self.gpio_heads_stop, RPIO.IN, pull_up_down=RPIO.PUD_DOWN)
        self.heads = -1 # -1 - before heads, 0 - heads, 1 - after heads 
    def __del__(self):
        RPIO.cleanup()
    def watch_start(self, start_callback):
        RPIO.add_interrupt_callback(self.gpio_heads_start, start_callback, edge='rising', debounce_timeout_ms=500, pull_up_down=RPIO.PUD_DOWN)
        RPIO.wait_for_interrupts(threaded=True)
    def watch_stop(self, stop_callback):
        RPIO.add_interrupt_callback(self.gpio_heads_stop, stop_callback, edge='rising', debounce_timeout_ms=500, pull_up_down=RPIO.PUD_DOWN)
        RPIO.wait_for_interrupts(threaded=True)