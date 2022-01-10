import adafruit_requests
import adafruit_tca9548a
import board
import busio
import microcontroller
import rtc
import socketpool
import ssl
import time
import traceback
import wifi

from adafruit_datetime import datetime, timedelta

from apps import *
from display import BetterSSD1306_I2C, DisplayGroup


display_group = None


def reset():
    if display_group:
        try:
            display_group.render_string('RESET', center=True)
            display_group.show()
        except Exception:
            pass

    time.sleep(30)
    microcontroller.reset()


# Get wifi details and more from a secrets.py file
try:
    from secrets import secrets
except ImportError:
    print('WiFi secrets are kept in secrets.py, please add them there!')
    raise

# Get configuration from a conf.py file
try:
    from conf import conf
except ImportError:
    print('No configuration found in conf.py, please add them there!')
    raise

WIDTH = 128
HEIGHT = 64

SDA = board.IO10
SCL = board.IO11

i2c = busio.I2C(SCL, SDA, frequency=1400000)

if i2c.try_lock():
    print('i2c.scan():' + str(i2c.scan()))
    i2c.unlock()

tca = adafruit_tca9548a.TCA9548A(i2c)
display_group = DisplayGroup(
    [BetterSSD1306_I2C(WIDTH, HEIGHT, tca[i]) for i in range(5)])

print('My MAC addr:', [hex(i) for i in wifi.radio.mac_address])

display_group.render_string('wifi setup', center=True)
display_group.show()
time.sleep(1)

connected = False

while not connected:
    fail_count = 0
    for wifi_conf in secrets:
        try:
            print('Connecting to {}'.format(wifi_conf['ssid']))
            display_group.clear()
            display_group.render_string('{0} {1}'.format(font.CHAR_WIFI, wifi_conf['ssid'][:8]), center=False)
            display_group.show()
            time.sleep(1)
            wifi.radio.connect(wifi_conf['ssid'], wifi_conf['password'])
            print('Connected to {}!'.format(wifi_conf['ssid']))
            print('My IP address is', wifi.radio.ipv4_address)
            display_group.clear()
            display_group.render_string('{0} '.format(font.CHAR_CHECK), center=True)
            display_group.show()
            time.sleep(1)
            connected = True
            break
        except ConnectionError:
            fail_count += 1
            print('Connection to {} has failed. Trying next ssid...'.format(wifi_conf['ssid']))
            display_group.clear()
            display_group.render_string('{0} '.format(font.CHAR_CROSS), center=True)
            display_group.show()
            time.sleep(1)

    if fail_count == len(secrets):
        display_group.clear()
        display_group.render_string('no wifi!', center=True)
        display_group.show()
        time.sleep(5)
        display_group.clear()
        display_group.render_string('scanning..', center=True)
        display_group.show()
        time.sleep(5)

pool = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())


# Initialize datetime
class RTC:

    def __init__(self):
        self.timezone = conf.get('timezone', 'Europe/Prague')
        self.__load_time = None
        self.__datetime = None

    @property
    def datetime(self):
        if not self.__datetime:
            dt = datetime.fromisoformat(requests.get('https://worldtimeapi.org/api/timezone/' + self.timezone).json()['datetime'])
            self.__load_time = time.monotonic()
            self.__datetime = datetime.fromtimestamp(dt.timestamp()) + dt.utcoffset()

        return (self.__datetime + timedelta(seconds=time.monotonic() - self.__load_time)).timetuple()


try:
    display_group.clear()
    display_group.render_string('TIME  INIT', center=True)
    display_group.show()
    rtc.set_time_source(RTC())
except Exception as e:
    traceback.print_exception(type(e), e, e.__traceback__)
    reset()

APPS = {
    'auto_contrast': AutoContrastApp,
    'crypto': CryptoApp,
    'time': TimeApp,
    'blockheight': BlockHeight,
    'halving': Halving,
    'fees': Fees,
    'text': Text,
    'marketcap': MarketCap,
    'moscow_time': MoscowTime,
    'difficulty': Difficulty,
    'temperature': Temperature,
}


def main():
    apps = []

    # Initialize all apps
    display_group.clear()
    display_group.render_string('APPS  INIT', center=True)
    display_group.show()
    for app_conf in conf['apps']:
        name = app_conf.pop('name')

        try:
            apps.append(APPS[name](display_group, requests, **app_conf))
        except KeyError:
            raise ValueError('Unknown app {}'.format(name))
        except Exception as e:
            print('Initialization of application {} has failed'.format(APPS[name].__name__))
            traceback.print_exception(type(e), e, e.__traceback__)

    # Run apps
    while True:
        for app in apps:
            try:
                app.run()
            except Exception as e:
                print('Application {} has crashed'.format(app.__class__.__name__))
                traceback.print_exception(type(e), e, e.__traceback__)
                reset()


if __name__ == '__main__':
    main()
