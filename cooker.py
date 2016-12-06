#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
log_format = '%(levelname)s | %(asctime)-15s | %(message)s'
logging.basicConfig(format=log_format, level=logging.DEBUG)
import RPIO_wrap.RPIO as RPIO
import time
logger = logging.getLogger(__name__)
file_handler = logging.FileHandler('moonshine.log')
formatter = logging.Formatter(log_format)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


class Cooker(object):
    powers = (120, 300, 600, 800, 1000, 1200, 1400, 1600, 1800, 2000)
    press_timeout = 1
    max_power_index = len(powers)-1
    power_max = powers[-1]
    power_min = powers[0]

    def __init__(self, gpio_on_off, gpio_up, gpio_down):
        self.gpio_on_off = gpio_on_off
        RPIO.setup(self.gpio_on_off, RPIO.OUT, initial=RPIO.HIGH)
        self.gpio_up = gpio_up
        RPIO.setup(self.gpio_up, RPIO.OUT, initial=RPIO.HIGH)
        self.gpio_down = gpio_down
        RPIO.setup(self.gpio_down, RPIO.OUT, initial=RPIO.HIGH)
        self.power_index = 6  # 1400W
        self.state_on = False
        self.target_power_index = 0

    def release(self):
        print("cooker.release")
        self.switch_off()
        RPIO.cleanup()

    def click_button(self, gpio_port_num):
        RPIO.output(gpio_port_num, 0)
        time.sleep(0.5)
        RPIO.output(gpio_port_num, 1)
        logger.debug('clicked GPIO_port={gpio}'.format(gpio=gpio_port_num))

    def switch_on(self, force_mode=False):
        if force_mode:
            self.state_on = False
        if not self.state_on:
            self.click_button(self.gpio_on_off)
            self.power_index = 6  # 1400W
            self.state_on = True

    def switch_off(self, force_mode=False):
        if force_mode:
            self.state_on = True
        if self.state_on:
            print("switch_OFF")
            self.click_button(self.gpio_on_off)
            self.state_on = False

    def power_up(self):
        if self.power_index < self.max_power_index:
            self.click_button(self.gpio_up)
            self.power_index += 1
            logger.debug("power_up, new_index={}".format(self.power_index))
            return True
        else:
            logger.debug("power_up False, index={}".format(self.power_index))
            return False

    def set_power_max(self):
        time.sleep(self.press_timeout)
        while self.power_up():
            logger.debug("set_power_max loop, power={}".format(self.current_power()))
            time.sleep(self.press_timeout)

    def power_down(self):
        if self.power_index > 0:
            self.click_button(self.gpio_down)
            self.power_index -= 1
            logger.debug("power_down, new_index={}".format(self.power_index))
            return True
        else:
            logger.debug("power_down False, index={}".format(self.power_index))
            return False

    def set_power_min(self):
        time.sleep(self.press_timeout)
        while self.power_down():
            time.sleep(self.press_timeout)

    def set_power_600(self):
        self.switch_on()
        time.sleep(self.press_timeout)
        while self.current_power() > 600:
            self.power_down()
            logger.debug("power_600 loop, power={}".format(self.current_power()))
            time.sleep(self.press_timeout)

    def set_power(self, power):
        # TODO detect wrong power OR approximate
        self.target_power_index = self.powers.index(power)
        if self.power_index > self.target_power_index:
            change_power = self.power_down()
        else:
            change_power = self.power_up()
        time.sleep(self.press_timeout)
        while self.power_index != self.target_power_index:
            time.sleep(self.press_timeout)
            change_power()

    def current_power(self):
        return self.powers[self.power_index]
