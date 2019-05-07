#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Distibot main module
"""

from __future__ import print_function
import time
import collections
import ConfigParser
import io
import threading
import logging

from pushbullet import Pushbullet

from cooker import Cooker
import valve
import heads_sensor
import tsensor
import flow_sensor


class PBWrap(Pushbullet):
    """
        Pushbullet api calls wrapper
    """
    def __init__(self, api_key, emu_mode=False):
        if str(api_key).lower() == 'xxx':
            self.emu_mode = True
            logging.info('api_key=%s, set emu_mode True', api_key)
        else:
            self.emu_mode = emu_mode
            logging.info('set emu_mode=%s', emu_mode)

        if self.emu_mode:
            self.channels = []
        else:
            super(PBWrap, self).__init__(api_key)

    def get_channel(self, channel_tag=u"Billy's moonshine"):
        if self.emu_mode:
            return pb_channel_emu()
        else:
            return [x for x in self.channels if x.name == channel_tag][0]


class pb_channel_emu(object):

    def push_note(self, subject, msg):
        logging.info("subj=%s/msg=%s", subject, msg)


class Distibot(object):

    def __init__(self, conf_filename='distibot.conf'):
        logging.getLogger(__name__).addHandler(logging.NullHandler())
        self.parse_conf(conf_filename)
        self.outdir = 'output'  # TODO config
        self.Tcmd_prev = 'before start'
        self.Tcmd_last = 'before start'
        self.downcount = 0
        # количество шагов подряд с неожидаемым снижением температуры
        self.downcount_limit = 5
        self.csv_write_period = 3
        self.temperature_error_limit = 3
        self.temperature_over_limit = 3
        self.temperature_delta_limit = 0.3  # 30%
        self.stage = 'start'
        self.current_ts = time.localtime()
        self.pause_start_ts = 0
        self.pause_limit = 180
        self.cooker_period = 3600
        self.cooker_timeout = 3
        self.drop_period = 4000
        self.drop_timeout = 15
        self.T_sleep = 1
        self.csv_delay = 0
        self.water_on = False
        self.print_str = []
        self.dt_string = time.strftime("%Y-%m-%d-%H-%M")
        self.timers = []
        self.drop_timer = threading.Timer(self.drop_period,
                                          self.drop_container)
        self.timers.append(self.drop_timer)
        self.cooker_timer = threading.Timer(self.cooker_period,
                                            self.cooker_off)
        self.timers.append(self.cooker_timer)

        if self.config.has_option('tsensors', 'gpio_ts'):
            # TODO switch gpio to INPUT
            self.tsensors = tsensor.Tsensors(self.config)
            self.tsensors.get_t()
            # TODO Tsensors(dict)
            self.T_prev = self.tsensors.ts_data['boiler']

        self.loop_flag = True

        powers_list = self.config.get('cooker', 'cooker_powers').replace(' ', '').split(',')
        self.cooker = Cooker(gpio_on_off=self.config.getint(
            'cooker', 'gpio_cooker_on_off'),
                             gpio_up=self.config.getint(
                                 'cooker', 'gpio_cooker_up'),
                             gpio_down=self.config.getint(
                                 'cooker', 'gpio_cooker_down'),
                             gpio_special=self.config.getint(
                                 'cooker', 'gpio_cooker_special'),
                             powers=tuple(map(int, powers_list)),
                             init_power=self.config.getint(
                                 'cooker', 'cooker_init_power'),
                             special_power=self.config.getint(
                                 'cooker', 'cooker_special_power'),
                             do_init_special=self.config.getboolean(
                                 'cooker', 'init_special')
                             )
        self.power_for_heads = self.config.getint('cooker', 'power_for_heads')

        # self.cooker_current_power = self.cooker.current_power()
        self.cooker_current_power = None

        self.valve_water = valve.Valve(valve_gpio=self.config.getint(
            'valve_water',
            'gpio_valve_water'))
        self.valve_drop = valve.Valve(valve_gpio=self.config.getint(
            'valve_drop',
            'gpio_valve_drop'))

        self.valve3way = valve.DoubleValve(gpio_v1=self.config.getint(
            'dbl_valve',
            'gpio_dbl_valve_1'),
                                           gpio_v2=self.config.getint(
                                               'dbl_valve',
                                               'gpio_dbl_valve_2'))

        self.heads_sensor = \
            heads_sensor.Heads_sensor(hs_type=self.config.get(
                'heads_sensor',
                'hs_type'),
                                      gpio_heads_start=self.config.getint(
                                          'heads_sensor',
                                          'gpio_hs_start'),
                                      gpio_heads_finish=self.config.getint(
                                          'heads_sensor',
                                          'gpio_hs_finish'),
                                      timeout=1000)

        # self.flow_period = 10
        self.flow_sensor = flow_sensor.FlowSensor(gpio_fs=self.config.getint(
            'flow_sensor',
            'gpio_fs'))
        self.flow_period = self.config.getint('flow_sensor', 'flow_period')

        self.pb = PBWrap(self.config.get('pushbullet', 'api_key'))
        self.pb_channel = self.pb.get_channel()
        self.coord = []
        self.coord_time = []
        self.coord_temp = []
        self.coord_temp_condenser = []
        self.log = open('{}/sensor-{}.csv'.format(self.outdir, self.dt_string),
                        'w', 0)  # 0 - unbuffered write

    def parse_conf(self, conf_filename):
        # Load and parse the conf file
        with open(conf_filename) as f:
            dib_config = f.read()
            self.config = ConfigParser.RawConfigParser(allow_no_value=True)
            self.config.readfp(io.BytesIO(dib_config))

    def load_script(self, play_filename):
        with open(play_filename, 'r') as script:
            self.Tsteps = collections.OrderedDict(sorted(eval(
                                                  script.read()).items(),
                                                  key=lambda t: t[0])
                                                  )
        self.set_Tsteps()
        # TODO check methods existance

    def load_play(self, play_filename):
        with open(play_filename, 'r') as script:
            self.Tsteps = collections.OrderedDict(sorted(eval(
                                                  script.read()).items(),
                                                  key=lambda t: t[0])
                                                  )
        logging.debug('type(Tsteps)=%s, Tsteps=%s', type(self.Tsteps), self.Tsteps)
        self.parse_play()

    def parse_play(self):
        self.Tkeys = self.Tsteps.keys()
        logging.debug('type=%s, Tkeys=%s', type(self.Tkeys), self.Tkeys)

        self.Tstage = self.Tkeys.pop(0)
        logging.debug('type=%s, Tstage[0]=%s', type(self.Tstage), self.Tstage)
        self.Tstep_current = self.Tsteps.pop(self.Tstage)
        logging.debug('type=%s, Tstep_current=%s', type(self.Tstep_current), self.Tstep_current)
        #self.Tsensor, self.Tcmd = self.Tsteps[self.Tstage]
        #logging.debug('Tsensor=%s, Tcmd=%s', self.Tsensor, self.Tcmd)

    def set_Tsteps(self):
        self.Tkeys = self.Tsteps.keys()
        self.Tstage = self.Tkeys.pop(0)
        self.Tcmd = self.Tsteps.pop(self.Tstage)
        # print(self.Tsteps)

    def send_msg(self, msg_subj, msg_body):
        logging.info("send_msg: subj={0}, msg='{1}'".format(
                                                     msg_subj, msg_body))
        msg_body = "{}: {}".format(time.strftime("%Y-%m-%d %H:%M"), msg_body)
        for i in range(1, 4):
            try:
                self.pb_channel.push_note(msg_subj, msg_body)
            except Exception:
                logging.exception('exception in send_msg[{0}]'.format(i))
                time.sleep(1)
            else:
                break

    def save_coord_file(self):
        logging.debug('coordinates to save time=%s, boiler=%s, condenser=%s',
                      len(self.coord_time), len(self.coord_temp), len(self.coord_temp_condenser))
        save_coord = open('{}/{}.dat'.format(self.outdir, self.dt_string), 'w')
        for i_time, i_temp, i_temp_condenser in zip(self.coord_time, self.coord_temp, self.coord_temp_condenser):
            save_str = '{}^{}^{}\n'.format(i_time, i_temp, i_temp_condenser)
            save_coord.write(save_str)
        save_coord.close()
        logging.debug('coordinates saved')

    def release(self):
        for t in self.timers:
            t.cancel()
        self.flow_sensor.release()
        self.cooker.release()
        self.valve3way.release()
        self.valve_water.release()
        self.valve_drop.release()
        self.heads_sensor.release()

    def csv_write(self):
        self.print_str.append(time.strftime("%H:%M:%S", self.current_ts))
        self.print_str.append(str(self.tsensors.ts_data['boiler']))
        try:
            t2 = self.tsensors.ts_data['condenser']
        except KeyError:
            t2 = 0
        self.print_str.append(str(t2))
        self.print_str.append(str(self.flow_sensor.clicks))
        self.print_str.append(str(self.flow_sensor.hertz))
        # self.print_str.append(str(self.tsensors.ts_data['condenser']))
        # logging.debug('ts_data={0}'.format(self.tsensors.ts_data))
        if self.csv_delay >= self.csv_write_period:
            self.csv_delay = 0
            print(','.join(self.print_str), file=self.log)
        elif self.Tcmd_last != self.Tcmd_prev:
            self.print_str.append(self.Tcmd_last)
            self.Tcmd_prev = self.Tcmd_last
            print(','.join(self.print_str), file=self.log)

        self.print_str = []
        self.csv_delay += self.T_sleep

    def do_cmd(self):
        self.Tcmd_last = self.Tcmd.__name__
        self.Tcmd()
        # TODO добавить t холодильника, если есть датчик
        self.send_msg("Превысили {0}".format(self.Tstage),
                      "t в кубе={0}, команда={1}".format(
                        self.tsensors.ts_data['boiler'], self.Tcmd.__name__))

        try:
            self.Tstage = self.Tkeys.pop(0)
        except IndexError:
            self.Tstage = 999.0
            self.Tcmd = self.do_nothing
        else:
            self.Tcmd = self.Tsteps.pop(self.Tstage)

    #def run_cmd(self, tsensor_id):
        #if tsensor_id not in self.Tstep_current.keys():
        #    return
    def run_cmd(self):
        tsensor_id, self.Tmethod = self.Tstep_current.popitem()
        self.Tcmd_last = self.Tmethod.__name__
        self.Tmethod()
        # TODO добавить t холодильника, если есть датчик
        self.send_msg("Превысили {0}".format(self.Tstage),
                      "ts_data={0}, команда={1}".format(
                        self.tsensors.ts_data, self.Tcmd_last))

        try:
            self.Tstage = self.Tkeys.pop(0)
        except IndexError:
            self.Tstage = 999.0
            self.Tstep_current['boiler'] = self.do_nothing  # dirty patch
        else:
            # prev: self.Tcmd = self.Tsteps.pop(self.Tstage)
            self.Tstep_current = self.Tsteps.pop(self.Tstage)

    def temperature_loop(self):
        over_cnt = 0
        t_failed_cnt = 0
        while self.loop_flag:
            if not self.tsensors.get_t():
                self.send_msg("Аварийное отключение",
                              "Сбой получения температуры, \
tsensors={0}".format(self.tsensors))
                self.stop_process()
                self.release()
                continue
            # для графика на сайте и протокола
            self.current_ts = time.localtime()
            self.coord_time.append(time.strftime("%H:%M:%S", self.current_ts))
            self.coord_temp.append(self.tsensors.ts_data['boiler'])
            self.coord_temp_condenser.append(self.tsensors.ts_data['condenser'])

            if self.tsensors.t_over(self.Tstep_current.keys()[0], self.Tstage):
                over_cnt += 1

            if over_cnt > self.temperature_over_limit or \
               self.Tstage == 0.0:
                over_cnt = 0
                self.run_cmd()

            self.csv_write()
            time.sleep(self.T_sleep)

        logging.info('temperature_loop exiting')

    def do_nothing(self, gpio_id=-1, value="-1"):
        print("do_nothing "
              + time.strftime("%H:%M:%S")
              + ", gpio_id=" + str(gpio_id)
              + ", value=" + str(value), file=self.log)
        pass

    def start_process(self):
        self.cooker_on()
        self.stage = 'heat'
        # moved to start_water()
        # self.drop_timer.start()
        logging.debug('stage is "{}"'.format(self.stage))

    def stop_process(self):
        if self.stage == 'finish':
            logging.info('already in finsh stage')
        else:
            self.loop_flag = False
            time.sleep(self.T_sleep+0.5)
            self.stage = 'finish'  # before cooker_off!
            self.cooker_off()
            logging.debug('stage is "{}"'.format(self.stage))
            self.save_coord_file()

    def cooker_off(self):
        self.cooker_timer.cancel()
        if self.cooker_timer in self.timers:
            self.timers.remove(self.cooker_timer)

        # TODO simplify
        if self.cooker.power_index:
            self.cooker_current_power = self.cooker.current_power()
            self.cooker.switch_off()

        if self.stage == 'finish':
            loc_str = "Финиш"
        else:
            self.cooker_timer = threading.Timer(self.cooker_timeout,
                                                self.cooker_on)
            self.timers.append(self.cooker_timer)
            self.cooker_timer.start()
            loc_str = "Установлен таймер на {}".format(self.cooker_timeout)

        self.send_msg("Нагрев отключён", loc_str)

    def cooker_on(self):
        self.cooker_timer.cancel()
        self.timers.remove(self.cooker_timer)

        # TODO simplify
        if self.cooker_current_power is not None and \
           self.cooker_current_power > 0:
            self.cooker.switch_on(self.cooker_current_power)
        else:
            self.cooker.switch_on()

        self.cooker_timer = threading.Timer(self.cooker_period,
                                            self.cooker_off)
        self.timers.append(self.cooker_timer)
        self.cooker_timer.start()
        self.send_msg("Нагрев включён",
                      "Установлен таймер на {}".format(self.cooker_period))

    def heat_on_pause(self):
        self.cooker_off()
        self.pause_start_ts = time.time()
        self.stage = 'pause'
        logging.debug('stage is "{}"'.format(self.stage))

    def heat_for_heads(self):
        logging.debug('inside heat_for_heads')
        self.cooker.set_power(self.power_for_heads)
        if 'heat' != self.stage:  # если и так фаза нагрева, выходим
            self.stage = 'heat'
            logging.debug('stage is "{}"'.format(self.stage))

    def heads_started(self, gpio_id=-1):
        logging.debug('inside heads_started')
        if self.heads_sensor.flag_ignore_start:
            logging.info('flag_ignore_start detected!')
        else:
            if 'heads' == self.stage:
                # ? Never will occured
                logging.debug('stage is already heads. Skipping')
            else:
                self.stage = 'heads'
                logging.debug('stage set to "{}"'.format(self.stage))
                self.Tcmd_last = 'heads_started'
                if gpio_id > 0:
                    self.send_msg("Стартовали головы",
                                  "gpio_id={}".format(gpio_id))
                    # call heads_sensor.ignore_start()
                    self.heads_sensor.watch_finish(self.heads_finished)
                logging.debug('after watch_finish')

    def heads_finished(self, gpio_id=-1):
        logging.debug('inside heads_finished')
        if self.heads_sensor.flag_ignore_finish:
            logging.info('flag_ignore_finish detected!')
        else:
            if 'heads' != self.stage:
                logging.debug('NOT heads, stage="{}". Skipping'.
                              format(self.stage))
                pass
            else:
                self.stage = 'body'
                logging.debug('stage set to "{}"'.format(self.stage))
                self.Tcmd_last = 'heads_finished'
                if gpio_id > 0:
                    self.send_msg("Закончились головы",
                                  "gpio_id={}".format(gpio_id))
                    self.heads_sensor.ignore_finish()
                self.valve3way.way_2()  # way for body
                self.cooker.set_power(1400)  # TODO from config?
                self.start_water()

    def start_watch_heads(self):
        logging.debug('inside start_watch_heads')
        self.start_water()
        self.cooker.set_power(self.power_for_heads)
        self.heads_sensor.watch_start(self.heads_started)
        self.valve3way.way_1()

    def wait4body(self):
        # self.cooker_on()
        self.cooker.set_power(1400)
        self.start_water()
        self.valve3way.way_2()
        self.stage = 'body'
        logging.info('stage is "{}"'.format(self.stage))

    def set_stage_body(self):
        self.stage = 'body'

    def start_water(self):
        if not self.water_on:
            self.valve_water.power_on_way()
            self.water_on = True
            self.flow_timer = threading.Timer(self.flow_period, self.no_flow)
            self.timers.append(self.flow_timer)
            self.flow_timer.start()
            self.flow_sensor.watch_flow(self.flow_detected)
            self.drop_timer.start()
            logging.info('water_on={}, flow_timer.is_alive={}'.format(
                          self.water_on, self.flow_timer.is_alive()))

    def drop_container(self):
        self.drop_timer.cancel()
        self.timers.remove(self.drop_timer)

        self.valve_drop.power_on_way()
        logging.debug('drop is on')
        self.send_msg("Сброс сухопарника", "Клапан сброса включён")

        self.drop_timer = threading.Timer(self.drop_timeout,
                                          self.close_container)
        self.timers.append(self.drop_timer)
        self.drop_timer.start()

    def close_container(self):
        self.drop_timer.cancel()
        self.timers.remove(self.drop_timer)

        self.valve_drop.switch_off()
        logging.debug('drop is off')
        self.send_msg("Сухопарник закрыт", "Клапан сброса отключён")

        self.drop_timer = threading.Timer(self.drop_period,
                                          self.drop_container)
        self.timers.append(self.drop_timer)
        self.drop_timer.start()

#    def stop_body_power_on(self):
#        self.stop_body()

    def stop_body(self):
        self.stage = 'tail'
        self.start_water()
        logging.debug('stage is "{}"'.format(self.stage))
        self.valve3way.way_3()
        self.send_msg("Закончилось тело", "Клапан выключен")

    def flow_detected(self, gpio_id):
        self.flow_timer.cancel()
        self.timers.remove(self.flow_timer)

        self.flow_timer = threading.Timer(self.flow_period, self.no_flow)
        self.timers.append(self.flow_timer)
        self.flow_timer.start()

        self.flow_sensor.handle_click()

    def no_flow(self):
        logging.warning("Нет потока охлаждения \
        за flow_period={}, Аварийное отключение".format(self.flow_period))
        self.send_msg("Аварийное отключение", "Нет потока охлаждения")
        # temporary do not STOP
        # self.stop_process()
        # self.release()

    def finish(self):
        logging.info('========== distibot.finish')
        self.stop_process()
        self.release()


if __name__ == "__main__":
    import argparse
    import os
    import sys
    import signal

    def dib_stop():
        global dib
        dib.stop_process()
        logging.info('after stop_process')
        dib.release()
        logging.info('after dib.release')

    def signal_handler(signal, frame):
        logging.info('Catched signal {}'.format(signal))
        dib_stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGHUP, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGUSR1, signal_handler)

    def segv_handler(signal, frame):
        logging.info('Catched signal {}'.format(signal))
        logging.info('frame.f_locals={}'.format(frame.f_locals))
        logging.info('frame: filename={}, function={}, line_no={}'.format(
                      frame.f_code.co_filename,
                      frame.f_code.co_name, frame.f_lineno))
        dib_stop()

    signal.signal(signal.SIGSEGV, segv_handler)

    (prg_name, prg_ext) = os.path.splitext(os.path.basename(__file__))
    # conf_file = prg_name +".conf"

    parser = argparse.ArgumentParser(description='Distibot module')
    parser.add_argument('--conf', type=str, default="distibot.conf",
                        help='conf file')
    parser.add_argument('--play', type=str, default="dib-debug.play",
                        help='play file')
    parser.add_argument('--log_to_file', type=bool, default=True,
                        help='log destination')
    parser.add_argument('--log_level', type=str, default="DEBUG",
                        help='log level')
    args = parser.parse_args()

    numeric_level = getattr(logging, args.log_level, None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: {0}'.format(numeric_level))

    log_format = '[%(filename)-22s:%(lineno)4s - %(funcName)20s()] \
            %(levelname)-7s | %(asctime)-15s | %(message)s'
    # log_format = '%(asctime)-15s | %(levelname)-7s | %(message)s'

    if args.log_to_file:
        log_dir = ''
        log_file = log_dir + prg_name + ".log"
        logging.basicConfig(filename=log_file, format=log_format,
                            level=numeric_level)
    else:
        logging.basicConfig(stream=sys.stdout, format=log_format,
                            level=numeric_level)

    # end of prolog
    logging.info('Started')

    dib = Distibot(conf_filename=args.conf)
    # prev dib.load_script(args.play)
    dib.load_play(args.play)
    dib.temperature_loop()

    logging.info('Exit')
