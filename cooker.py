#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
import logging
# import io
from gpio_dev import GPIO_DEV, GPIO


class Cooker(GPIO_DEV):

    def __init__(self, gpio_on_off, gpio_up, gpio_down, gpio_special, powers, init_power, special_power, do_init_special):
        super(Cooker, self).__init__()
        self.gpio_on_off = gpio_on_off
        self.setup(self.gpio_on_off, GPIO.OUT, initial=GPIO.LOW)
        #
        self.gpio_up = gpio_up
        self.setup(self.gpio_up, GPIO.OUT, initial=GPIO.LOW)
        #
        self.gpio_down = gpio_down
        self.setup(self.gpio_down, GPIO.OUT, initial=GPIO.LOW)
        #
        self.gpio_special = gpio_special
        self.setup(self.gpio_special, GPIO.OUT, initial=GPIO.LOW)
        #
        self.click_delay = 0.5
        self.state_on = False
        self.target_power_index = 0

        # powers = (120, 300, 600, 800, 1000, 1200, 1400, 1600, 1800, 2000)
        self.powers = powers
        self.max_power_index = len(powers)-1
        self.power_max = powers[-1]
        self.power_min = powers[0]
        self.do_init_special = do_init_special
        self.ini_power_index = self.powers.index(init_power)
        self.ini_special_index = self.powers.index(special_power)
        self.power_index = None
        # a right place is in switch_on()
        # if self.do_init_special:
        #    self.power_index = self.ini_special_index
        # else:
        #    self.power_index = self.ini_power_index

    def release(self):
        self.call_log()
        logging.info("cooker.release")
        self.switch_off()
        super(Cooker, self).release()

    def click_button(self, gpio_port_num):
        time.sleep(self.click_delay)  # для двух "нажатий" подряд
        self.output(gpio_port_num, GPIO.HIGH)
        time.sleep(self.click_delay)
        self.output(gpio_port_num, GPIO.LOW)
        # logging.debug('clicked port={gpio}'.format(gpio=gpio_port_num))

    def switch_on(self, power_value=None):
        self.call_log()
        if not self.state_on:
            self.click_button(self.gpio_on_off)
            self.power_index = self.ini_power_index
            self.state_on = True
            logging.info("switch_ON")
        if power_value is not None:
            logging.debug("switch_on, arg power_value={}".format(power_value))
            self.set_power(power_value)
            self.power_index = self.powers.index(power_value)
            logging.debug("switched on, current_power={}".format(self.current_power()))
        elif self.do_init_special:  # power_value is a priority
            self.click_button(self.gpio_special)
            self.power_index = self.ini_special_index
            self.do_init_special = False

    def switch_off(self):
        self.call_log()
        if self.state_on:
            logging.info("switch_OFF")
            self.click_button(self.gpio_on_off)
            self.state_on = False

    def power_up(self):
        if self.power_index < self.max_power_index:
            self.click_button(self.gpio_up)
            self.power_index += 1
            logging.debug("power_up, new_index={}, new_power={}".format(self.power_index, self.current_power()))
            return True
        else:
            logging.debug("power_up, False index={}, power={}".format(self.power_index, self.current_power()))
            return False

    def set_power_max(self):
        while self.power_up():
            pass
            logging.debug("set_power_max loop, power={}".format(self.current_power()))

    def power_down(self):
        if self.power_index > 0:
            self.click_button(self.gpio_down)
            self.power_index -= 1
            logging.debug("power_down, new_index={}, new_power={}".format(self.power_index, self.current_power()))
            return True
        else:
            logging.debug("power_down, False index={}, power={}".format(self.power_index, self.current_power()))
            return False

    def set_power_min(self):
        while self.power_down():
            pass
            logging.debug("set_power_min loop, power={}".format(self.current_power()))

    def set_power_600(self):
        self.switch_on()
        while self.current_power() > 600:
            self.power_down()
            logging.debug("power_600 loop, power={}".format(self.current_power()))

    def set_power_300(self):
        self.set_power(300)

    def set_power_1200(self):
        self.set_power(1200)

    def set_power_1800(self):
        self.set_power(1800)

    def set_power(self, power):
        # TODO detect wrong power OR approximate
        logging.debug("set_power arg_power={}".format(power))
        try:
            self.target_power_index = self.powers.index(power)
        # except LookupError:
        except Exception:
            logging.exception('set_power index error', exc_info=True)
            self.switch_off()
            self.switch_on()
        else:
            if self.power_index > self.target_power_index:
                change_power = self.power_down
                do_change = True
            elif self.power_index < self.target_power_index:
                change_power = self.power_up
                do_change = True
            else:
                do_change = False
            while do_change:
                change_power()
                do_change = (self.power_index != self.target_power_index)

    def current_power(self):
        return self.powers[self.power_index]

if __name__ == '__main__':
    from time import sleep
    import argparse
    import os
    import sys
    from configparser import ConfigParser

    class Cooker_tester(object):
        def __init__(self, conf_filename='distibot.conf'):
            self.config = ConfigParser()
            self.config.read(conf_filename)

            self.cooker = Cooker(gpio_on_off=self.config.getint('cooker', 'gpio_cooker_on_off'),
                                 gpio_up=self.config.getint('cooker', 'gpio_cooker_up'),
                                 gpio_down=self.config.getint('cooker', 'gpio_cooker_down'),
                                 gpio_special=self.config.getint('cooker', 'gpio_cooker_special'),
                                 powers=eval(self.config.get('cooker', 'cooker_powers')),
                                 init_power=self.config.getint('cooker', 'cooker_init_power'),
                                 special_power=self.config.getint('cooker', 'cooker_special_power'),
                                 do_init_special=self.config.getboolean('cooker', 'init_special')
                                 )

        def load_script(self, play_file_name):
            script = open(play_file_name, 'r')
            self.play = eval(script.read())
            script.close()

        def play_script(self):
            for play_stage in self.play:
                logging.debug('=== run play_stage={0}'.format(play_stage))
                self.cooker.set_power(play_stage)
                logging.info('>>> current_power={}'.format(self.cooker.current_power()))
                sleep(3)

    (prg_name, prg_ext) = os.path.splitext(os.path.basename(__file__))

    parser = argparse.ArgumentParser(description='Distibot "cooker" module')
    parser.add_argument('--conf', type=str, default="distibot.conf", help='conf file')
    parser.add_argument('--play', type=str, default="cooker.play", help='play file')
    parser.add_argument('--log_to_file', type=bool, default=False, help='log destination')
    parser.add_argument('--log_level', type=str, default="DEBUG", help='log level')
    args = parser.parse_args()

    numeric_level = getattr(logging, args.log_level, None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % numeric_level)

    # log_format = '[%(filename)-20s:%(lineno)4s - %(funcName)20s()] %(levelname)-7s | %(asctime)-15s | %(message)s'
    log_format = '%(asctime)-15s | %(levelname)-7s | %(message)s'

    if args.log_to_file:
        log_dir = ''
        log_file = log_dir + prg_name + ".log"
        logging.basicConfig(filename=log_file, format=log_format, level=numeric_level)
    else:
        logging.basicConfig(stream=sys.stdout, format=log_format, level=numeric_level)

    logging.info('Started')
    ckt = Cooker_tester(args.conf)

    ckt.cooker.switch_on()
    sleep(2)

    # cooker_play = (240, 150, 80, 150)
    ckt.load_script(args.play)
    ckt.play_script()

    bck_power = ckt.cooker.current_power()
    logging.debug('bck_power={}'.format(bck_power))

    ckt.cooker.switch_off()
    sleep(2)
    ckt.cooker.switch_on(bck_power)
    sleep(2)

    ckt.cooker.release()

    logging.info('Finished')
