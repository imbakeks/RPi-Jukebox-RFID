#!/usr/bin/env python3
# Rotary volume knob

from RPi import GPIO
from time import sleep
import time
import logging
from threading import Timer
import mpd
import os

# Helpers
# --------------
def clamp(val, minimum, maximum):
    """ Clamp value between minimum and maximum """
    return max(minimum, min(val, maximum))

# From https://stackoverflow.com/a/13151299
class RepeatedTimer(object):
    def __init__(self, interval, function, *args, **kwargs):
        self._timer     = None
        self.interval   = interval
        self.function   = function
        self.args       = args
        self.kwargs     = kwargs
        self.is_running = False
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        if not self.is_running:
            self._timer = Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False

# From https://github.com/modmypi/Rotary-Encoder/blob/master/rotary_encoder.py
class RotaryEncoder:
    counter = 0
    logger = logging.getLogger("RotaryEncoder")

    def __init__(self, pinA, pinB, functionCallIncr=None, functionCallDecr=None, timeBase=0.1, 
                name='RotaryEncoder'):
        self.name = name
        # persist values
        self.clk = pinA
        self.dt = pinB
        
        # Don't use broken increment and decrement methods for volume up/ down. Eventually will cause 
        # huge jumps in volume and suddenly it will be full volume or no volume...
        # Instead call mpc directly from here ...
        # self.functionCallbackIncr = functionCallIncr
        # self.functionCallbackDecr = functionCallDecr
        self.timeBase = timeBase
        self.mpc = mpd.MPDClient()
        self.mpdHost = 'localhost'
        self.mpdPort = 6600       
        self.lock = False
        self.minVolume = 0
        self.maxVolume = 100        
        self.stepSize = 3
        self.cachedConfigTimestamp = -1
        self.readConfig()
        self.lastIncreaseTime = 0
        self.lastDecreaseTime = 0

        # setup pins
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.clk, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.dt, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.clkLastState = GPIO.input(self.clk)
        GPIO.add_event_detect(self.clk, GPIO.BOTH, callback=self.check)
        GPIO.add_event_detect(self.dt, GPIO.BOTH, callback=self.check)

    def __del__(self):
        GPIO.remove_event_detect(self.clk)
        GPIO.remove_event_detect(self.dt)

    def readConfig(self):
        filename ="/home/pi/RPi-Jukebox-RFID/settings/global.conf" 
        timestamp = os.stat(filename).st_mtime
        if timestamp == self.cachedConfigTimestamp:
            return

        self.cachedConfigTimestamp = timestamp        

        with open(filename, "r") as config:
            for line in config:
                splitLine = line.split("=")
                key = str(splitLine[0])
                val = splitLine[1].replace('\n', '').replace('"', '')
                self.logger.info("Key: " + key + ", Val: " + val)
               
                if key == "AUDIOVOLMAXLIMIT":
                    self.maxVolume = int(val)
                elif key == 'AUDIOVOLCHANGESTEP':
                    self.stepSize = int(val)
                # Don't use min volume limit as it will be clamped to 0.01 by Phoniebox somewhere ... 
                # but we want to go to 0
                #elif key == 'AUDIOVOLMINLIMIT': 
                    #self.minVolume = int(val)

    def check(self, pin):
        if self.lock:
            return

        self.readConfig()

        self.lock = True
        self.clkState = GPIO.input(self.clk)
        self.dtState = GPIO.input(self.dt)        
        if self.clkState != self.clkLastState:
            try:
                self.mpc.disconnect()
                self.mpc.connect(self.mpdHost, self.mpdPort)
                currentVolume = int(self.mpc.status()["volume"])
                if self.dtState != self.clkState:
                    self.counter += 1

                    if time.time() - self.lastDecreaseTime > 0.1:
                        self.lastIncreaseTime = time.time()                    
                        currentVolume += int(self.stepSize / 2.0)
                    # self.functionCallbackIncr()
                else:
                    self.counter -= 1
                    if time.time() - self.lastIncreaseTime > 0.1:
                        self.lastDecreaseTime = time.time()
                        currentVolume -= int(self.stepSize / 2.0)
                    # self.functionCallbackDecr()

                #self.logger.info("Max: "+ str(self.maxVolume) + ", Min: " + str(self.minVolume) + ", Step: " + str(self.stepSize))
                currentVolume = clamp(currentVolume, self.minVolume, self.maxVolume)
                self.mpc.setvol(currentVolume)               
            except ConnectionError:
                pass

            self.clkLastState = self.clkState
        self.lock = False
            
