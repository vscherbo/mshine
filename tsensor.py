#!/usr/bin/python -t
# -*- coding: utf-8 -*-

# from __future__ import print_function
try:
    import w1thermsensor
    assert w1thermsensor
except ImportError:
    import stub_w1thermsensor as w1thermsensor
import logging
log_format = '%(levelname)s | %(asctime)-15s | %(message)s'
logger = logging.getLogger(__name__)
# file_handler = logging.FileHandler('moonshine.log')
# formatter = logging.Formatter(log_format)
# file_handler.setFormatter(formatter)
# logger.addHandler(file_handler)

class Tsensor(w1thermsensor.W1ThermSensor):
    def __init__(self, sensor_type=None, sensor_id=None, emu_mode=False):
        self.curr_T = 20
        if emu_mode:
            self.setup_emu_mode()
        else:
            try:
                # sensor = W1ThermSensor(W1ThermSensor.THERM_SENSOR_DS18B20, "0000066c6502")
                # ll /sys/bus/w1/devices/
                self.emu_mode = False
                self.sensor = w1thermsensor.W1ThermSensor(sensor_type=sensor_type, sensor_id=sensor_id)
            except w1thermsensor.core.KernelModuleLoadError:
                self.setup_emu_mode()

    def step_emu_mode(self, x):
        if x < 76:
            return 1.0
        elif x < 80:
            return 0.1
        else:
            return 0.5

    def setup_emu_mode(self):
        self.emu_mode = True
        self.Trange = [x for x in range(1, 99)]
        # self.emu_iterator = iter(self.Trange)

    def get_temperature(self, unit=w1thermsensor.W1ThermSensor.DEGREES_C):
        if self.emu_mode:
            self.curr_T += self.step_emu_mode(self.curr_T)
            logger.debug('emu_mode get_temperature={}'.format(self.curr_T))
            return self.curr_T
        else:
            loc_T = self.sensor.get_temperature(unit)
            # logger.debug('get_temperature loc_T={}'.format(loc_T))
            return loc_T
