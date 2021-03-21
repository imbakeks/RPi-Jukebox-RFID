# Author: imbakeks

import time
import logging
from rpi_ws281x import *
import argparse
import random
import mpd
import signal
import RPi.GPIO as GPIO

from .simple_button import SimpleButton

# LED strip configuration:
LED_COUNT      = 12      # Number of LED pixels.
LED_PIN        = 18      # GPIO pin connected to the pixels (18 uses PWM!).
#LED_PIN        = 10      # GPIO pin connected to the pixels (10 uses SPI /dev/spidev0.0).
LED_FREQ_HZ    = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA        = 10      # DMA channel to use for generating signal (try 10)
LED_BRIGHTNESS = 32     # Set to 0 for darkest and 255 for brightest
LED_INVERT     = False   # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL    = 0       # set to '1' for GPIOs 13, 19, 41, 45 or 53

class LEDRing(SimpleButton):
    logger = logging.getLogger("LEDRing")

    def __init__(self, pin, action=lambda *args: None, name=None, bouncetime=500, edge=GPIO.FALLING,
                 hold_time=.1, hold_repeat=False, pull_up_down=GPIO.PUD_UP):                 
        super().__init__(pin, action, name, bouncetime, edge, hold_time, hold_repeat, 
            pull_up_down)

        self.logger.info("LEDRing init")

        # MPC client to check for connection
        self.mpc = mpd.MPDClient()
        self.mpdHost = 'localhost'
        self.mpdPort = 6600
        self.mpdHadConnection = False

        self.logger.info("MPD Client init")

        # Shutdown flag, set on shutdown 
        self.shuttingDown = False
        signal.signal(signal.SIGTERM, self.onShutdown)

        # Create NeoPixel object with appropriate configuration.         
        self.strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)

        self.logger.info("Strip init")

        # Intialize the library (must be called once before other functions).
        self.strip.begin()

        self.logger.info("Strip begin")

        # Clean state at the beginning
        self.fireInterval = 100
        self.fireLastTime = 0
        self.colorWipe(Color(0,0,0), 1)

        self.logger.info("Start loop")
        self.loop()

    def onShutdown(self, sig, frame):
        """ Event called on shutdown """
        self.shuttingDown = True

    def has_mpd_connection(self):
        """ Returns True if mpc is connected, False if not """
        self.mpc.disconnect()
        try:
            self.mpc.connect(self.mpdHost, self.mpdPort)
            self.mpc.ping()
            self.mpc.disconnect()
            return True
        except ConnectionError:
            return False

    # Define functions which animate LEDs in various ways.
    def colorWipe(self, color, wait_ms=50):
        """Wipe color across display a pixel at a time."""
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, color)
            self.strip.show()
            time.sleep(wait_ms/1000.0)

    def colorWipeInstant(self, color):
        """Wipe color across display all pixels."""
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, color)            
        
        self.strip.show()

    def simulateFire (self, wait_ms=500):
        """Simulates fire according to https://www.az-delivery.de/en/blogs/azdelivery-blog-fur-arduino-und-raspberry-pi/eine-stimmungslaterne"""
        nowmilli = round(time.time() * 1000)
        numPixels = self.strip.numPixels()
        numPixelsRange = range(self.strip.numPixels())
        diff = nowmilli - self.fireLastTime
        lightValue = [0] * (numPixels * 3  + 2)
        if diff >= self.fireInterval:
            self.fireInterval = random.randrange(150, 200)
            self.fireLastTime = nowmilli
            for i in numPixelsRange:
                # For each pixel..
                lightValue[i * 3] = random.randrange(240, 255); # 200
                lightValue[i * 3 + 1] = random.randrange(30, 60); # 50
                lightValue[i * 3 + 2] = 0

            # Switch some lights darker
            for i in numPixelsRange:
                selected = random.randrange(numPixels)
                lightValue[selected * 3] = random.randrange(50, 60)
                lightValue[selected * 3 + 1] = random.randrange(5, 10)
                lightValue[selected * 3 + 2] = 0

            for i in numPixelsRange:
                # For each pixel...
                self.strip.setPixelColor(i, Color(lightValue[i * 3], lightValue[i * 3 + 1], lightValue[i * 3 + 2]))
                self.strip.show() # Send the updated pixel colors to the hardware.
                time.sleep(wait_ms/1000.0)

    def theaterChase(self, color, wait_ms=50, iterations=10):
        """Movie theater light style chaser animation."""
        for j in range(iterations):
            for q in range(3):
                for i in range(0, self.strip.numPixels(), 3):
                    self.strip.setPixelColor(i+q, color)
                self.strip.show()
                time.sleep(wait_ms/1000.0)
                for i in range(0, self.strip.numPixels(), 3):
                    self.strip.setPixelColor(i+q, 0)

    def wheel(self, pos):
        """Generate rainbow colors across 0-255 positions."""
        if pos < 85:
            return Color(pos * 3, 255 - pos * 3, 0)
        elif pos < 170:
            pos -= 85
            return Color(255 - pos * 3, 0, pos * 3)
        else:
            pos -= 170
            return Color(0, pos * 3, 255 - pos * 3)

    def rainbow(self, wait_ms=20, iterations=1):
        """Draw rainbow that fades across all pixels at once."""
        for j in range(256*iterations):
            for i in range(self.strip.numPixels()):
                self.strip.setPixelColor(i, self.wheel((i+j) & 255))
            self.strip.show()
            time.sleep(wait_ms/1000.0)
    
    def rainbowCycle(self, wait_ms=20, iterations=5):
        """Draw rainbow that uniformly distributes itself across all pixels."""
        for j in range(256*iterations):
            for i in range(self.strip.numPixels()):
                self.strip.setPixelColor(i, self.wheel((int(i * 256 / self.strip.numPixels()) + j) & 255))
            self.strip.show()
            time.sleep(wait_ms/1000.0)

    def theaterChaseRainbow(self, wait_ms=50):
        """Rainbow movie theater light style chaser animation."""
        for j in range(256):
            for q in range(3):
                for i in range(0, self.strip.numPixels(), 3):
                    self.strip.setPixelColor(i+q, self.wheel((i+j) % 255))
                self.strip.show()
                time.sleep(wait_ms/1000.0)
                for i in range(0, self.strip.numPixels(), 3):
                    self.strip.setPixelColor(i+q, 0)

    def loop(self):        
        """LED loop"""

        while True:
            try:
                if self.shuttingDown:
                    self.logger.info("Shutdown")                    
                    self.colorWipeInstant(Color(0,0,0))
                    break

                if not self.has_mpd_connection():
                    # Play wait for animation
                    self.mpdHadConnection = False
                    # self.theaterChase(Color(127, 127, 127))                
                    self.theaterChaseRainbow(10)
                    continue # Wait for mpd connection before continueing
                elif not self.mpdHadConnection:
                    self.logger.info("MPD connected")
                    # Play animation once on connection                    
                    self.mpdHadConnection = True
                    self.theaterChase(Color(0, 0, 127))

                # Pressed = Not playing
                if self.is_pressed:
                    self.simulateFire(100)
                # Released = Playing
                else:
                    self.rainbowCycle(5,1)
                    #self.colorWipe(Color(0,255,0), 25)
                    #self.colorWipe(Color(0,0,0), 25)
                
                # Ensure inifite loop but also make sure that there is always some sleep time to not
                # kill the cpu although all animations contain a sleep anyways, just to be sure
                time.sleep(0.1)
            except:
                break
