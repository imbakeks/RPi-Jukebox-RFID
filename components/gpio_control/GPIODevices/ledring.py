# Author: imbakeks

import time
import logging
from rpi_ws281x import *
import argparse
import random
import mpd
import signal
import RPi.GPIO as GPIO
import os.path

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

# Helpers
# --------------
def clamp(val, minimum, maximum):
    """ Clamp value between minimum and maximum """
    return max(minimum, min(val, maximum))

def clamp01(val):
    """ Clamp value between 0 and 1 """
    return clamp(val, 0.0, 1.0)

class ledcolor():
    """ Small wrapper for color """
    def __init__(self, r, g, b):
        self.r = r
        self.g = g
        self.b = b

    @staticmethod
    def encode(ledcolor):
        return Color(ledcolor.r, ledcolor.g, ledcolor.b)

    @staticmethod
    def decode(pixel):
        color = ledcolor(0,0,0)
        color.b = pixel & 0xff
        color.g = (pixel >> 8) & 0xff
        color.r = (pixel >> 16) & 0xff
        return color


class lerp():
    @staticmethod
    def number(start, end, alpha):
        return (alpha * end) + ((1.0-alpha) * start)
    
    @staticmethod
    def colorRGB(start, end, alpha):
        startCol = ledcolor.decode(start)
        endCol = ledcolor.decode(end)
        r = lerp.number(startCol.r, endCol.r, alpha)
        g = lerp.number(startCol.g, endCol.g, alpha)
        b = lerp.number(startCol.b, endCol.b, alpha)
        return Color(int(r), int(g), int(b))

# Animations
# --------------
class LEDRingAnimation():
    """ Base class for animations """
    def __init__(self, strip):
        self.deltaTime = 0.0
        self.currentTime = 0.0
        self.strip = strip        

    def reset(self):
        self.currentTime = 0.0

    def tick(self, deltaTime):
        self.deltaTime = deltaTime
        self.currentTime += self.deltaTime

    @staticmethod
    def posToRainbow(pos):
        """Generate rainbow colors across 0-255 positions."""
        if pos < 85:
            return Color(pos * 3, 255 - pos * 3, 0)
        elif pos < 170:
            pos -= 85
            return Color(255 - pos * 3, 0, pos * 3)
        else:
            pos -= 170
            return Color(0, pos * 3, 255 - pos * 3)

class LEDRingAnimationTimed(LEDRingAnimation):
    """ Base class for duration based animations """ 
    pass

    def __init__(self, strip, duration):
        self.duration = duration
        self.alpha = 0.0
        self.loop = False
        super().__init__(strip)

    def reset(self):
        super().reset()
        self.alpha = 0.0

    def tick(self, deltaTime):
        if self.loop and self.isFinished():
            self.currentTime = 0.0

        super().tick(deltaTime)
        self.alpha = clamp01(self.currentTime / self.duration)

    def isFinished(self):
        return self.currentTime > self.duration


class FadeAnimation(LEDRingAnimationTimed):
    """ Fade from start to end color in duration """
    pass    

    def __init__(self, strip, duration, starColor, endColor):
        self.startColor = starColor
        self.endColor = endColor        
        super().__init__(strip, duration)

    def tick(self, deltaTime):
        super().tick(deltaTime)
        color = lerp.colorRGB(self.startColor, self.endColor, self.alpha)

        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, color)

        self.strip.show()

class ColorWipeAnimation(LEDRingAnimationTimed):
    """ Wipe color across display a pixel at a time """
    pass

    def __init__(self, strip, duration, endColor):
        self.endColor = endColor        
        self.timeBetweenPixels = duration / LED_COUNT
        self.currentPixel = 0
        self.currentPixelShowTime = 0.0
        super().__init__(strip, duration)

    def reset(self):
        super().reset()
        self.currentPixel = 0
        self.currentPixelShowTime = 0.0

    def tick(self, deltaTime):
        super().tick(deltaTime)
        self.currentPixelShowTime += deltaTime

        if self.currentPixelShowTime >= self.timeBetweenPixels:
            self.currentPixelShowTime = 0.0
            self.strip.setPixelColor(self.currentPixel, self.endColor)
            self.strip.show()
            self.currentPixel += 1

class TheaterChase(LEDRingAnimation):
    """Movie theater light style chaser animation."""

    def __init__(self, strip, color, delay=0.01, iterations=1):
        self.color = color
        self.delay = delay
        self.iterations = iterations
        self.j = 0
        self.q = 0
        super().__init__(strip)

    def tick(self, deltaTime):
        super().tick(deltaTime)

        if self.currentTime < self.delay:
            return

        self.currentTime = 0

        self.q += 1
        if self.q > 2:
            self.q = 0
            self.j += 1
            if self.j > self.iterations:
                self.j = 0

        for i in range(0, self.strip.numPixels(), 3):
            self.strip.setPixelColor(i + self.q, self.color)

        self.strip.show()

        for i in range(0, self.strip.numPixels(), 3):
            self.strip.setPixelColor(i + self.q, 0)

class TheaterChaseRainbowAnimation(LEDRingAnimation):
    """Rainbow movie theater light style chaser animation."""
    pass

    def __init__(self, strip, delay = 0.01):
        self.delay = delay
        self.j = 0
        self.q = 0
        super().__init__(strip)

    def tick(self, deltaTime):
        super().tick(deltaTime)

        if self.currentTime < self.delay:
            return

        self.currentTime = 0

        self.q += 1
        if self.q > 2:
            self.q = 0
            self.j += 1
            if self.j > 255:
                self.j = 0

        for i in range(0, self.strip.numPixels(), 3):
            self.strip.setPixelColor(i + self.q, self.posToRainbow((i + self.j) % 255))
        
        self.strip.show()

        for i in range(0, self.strip.numPixels(), 3):
            self.strip.setPixelColor(i + self.q, 0)

class RaimbowAnimation(LEDRingAnimation):
    """Draw rainbow that fades across all pixels at once."""
    def __init__(self, strip, delay = 0.01):
        self.delay = delay
        self.iter = 0
        super().__init__(strip)

    def tick(self, deltaTime):
        super().tick(deltaTime)

        if self.currentTime < self.delay:
            return

        self.currentTime = 0

        self.iter += 1
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, self.posToRainbow((i + self.iter) & 255))

        self.strip.show()

class RainbowCycleAnimation(LEDRingAnimation):
    """Draw rainbow that uniformly distributes itself across all pixels."""
    def __init__(self, strip, delay = 0.01, invert = False):
        self.delay = delay
        self.invert = invert
        self.iter = 0
        super().__init__(strip)

    def tick(self, deltaTime):
        super().tick(deltaTime)

        if self.currentTime < self.delay:
            return

        self.currentTime = 0

        self.iter += 1
        for i in range(self.strip.numPixels()):
            index = i
            if self.invert:
                index = self.strip.numPixels() - i - 1
            self.strip.setPixelColor(index, self.posToRainbow((int(i * 256 / self.strip.numPixels()) + self.iter) & 255))

        self.strip.show()
        
class FireAnimation(LEDRingAnimation):    
    """Simulates fire according to https://www.az-delivery.de/en/blogs/azdelivery-blog-fur-arduino-und-raspberry-pi/eine-stimmungslaterne"""

    def __init__(self, strip, intervalMin = 0.25, intervalMax = 0.5):
        self.intervalMin = intervalMin
        self.intervalMax = intervalMax
        self.randomizeInterval()
        self.newLightValue = [0] * ((strip.numPixels() * 3) + 3)
        self.currentPixelToUpdate = 0                
        super().__init__(strip)
        self.randomizeNewFireColors()

    def randomizeInterval(self):
        self.fireInterval = (random.randrange(int(self.intervalMin * 1000), int(self.intervalMax * 1000))) / 1000.0

    def randomizeNewFireColors(self):
        numPixelsRange = range(self.strip.numPixels())
        numPixels = self.strip.numPixels()
        for i in numPixelsRange:
            self.newLightValue[i * 3] = random.randrange(240, 255)
            self.newLightValue[i * 3 + 1] = random.randrange(30, 60)
            self.newLightValue[i * 3 + 2] = 0

        # Switch some lights darker
        for i in numPixelsRange:
            selected = random.randrange(0, numPixels)
            self.newLightValue[selected * 3] = random.randrange(50, 60)
            self.newLightValue[selected * 3 + 1] = random.randrange(5, 10)
            self.newLightValue[selected * 3 + 2] = 0

    def tick(self, deltaTime):
        super().tick(deltaTime)

        self.currentTime += deltaTime
        if self.currentTime < 0.1:            
            return

        self.randomizeInterval()
        self.currentTime = 0.0

        if self.currentPixelToUpdate <= 0:
            self.randomizeNewFireColors()
        
        self.strip.setPixelColor(self.currentPixelToUpdate, Color(self.newLightValue[self.currentPixelToUpdate * 3], self.newLightValue[self.currentPixelToUpdate * 3 + 1], self.newLightValue[self.currentPixelToUpdate * 3 + 2]))

        self.strip.show()

        self.currentPixelToUpdate += 1
        if self.currentPixelToUpdate > self.strip.numPixels():
            self.currentPixelToUpdate = 0

# LED Ring main class
# --------------
class LEDRing(SimpleButton):
    logger = logging.getLogger("LEDRing")
    pass

    def __init__(self, pin, action=lambda *args: None, name=None, bouncetime=500, edge=GPIO.FALLING,
                 hold_time=.1, hold_repeat=False, pull_up_down=GPIO.PUD_UP):                 
        super().__init__(pin, action, name, bouncetime, edge, hold_time, hold_repeat, 
            pull_up_down)

        self.logger.info("LEDRing init")                

        # MPC client to check for connection
        self.mpc = mpd.MPDClient()
        self.mpdHost = 'localhost'
        self.mpdPort = 6600
        self.mpdConnected = False
        self.mpdHadConnection = False
        self.songCache = None

        self.logger.info("MPD Client init")

        # Shutdown flag, set on shutdown 
        self.killMe = False
        signal.signal(signal.SIGINT, self.exitRequested)
        signal.signal(signal.SIGTERM, self.exitRequested)

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
        # @todo: Would be better to start loop in subprocess/ thread
        self.loop()

    def exitRequested(self, sig, frame):
        """ Event called on shutdown """
        self.logger.info("Exit requested")
        self.killMe = True

    def checkWantsShutdown(self):
        """ Checks for tmp file stored by cleanshutd mod """
        return os.path.isfile("/tmp/cleanshutd")

    def isMpdConnected(self):
        """ Returns True if mpc is connected, False if not """        
        try:            
            self.mpc.disconnect()
            self.mpc.connect(self.mpdHost, self.mpdPort)
            self.mpc.ping()                
            self.mpdConnected = True            
            return True
        except ConnectionError:
            self.mpc.disconnect()
            return False

    def mpdSongChanged(self):
        """ Returns true if song has changed """
        if not self.mpdConnected:
            return False

        try:
            newSong = self.mpc.status()["song"]
            if newSong != self.songCache:
                self.songCache = newSong
                return True
        except KeyError:
            pass

        return False

    def mpdIsPlaying(self):
        """ Returns true if a song is playing """
        if not self.mpdConnected:
            return False

        return self.mpc.status()["state"] != "pause"

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
                lightValue[i * 3] = random.randrange(240, 255) # 200
                lightValue[i * 3 + 1] = random.randrange(30, 60) # 50
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
    
    def rainbowCycle(self, wait_ms=20, iterations=5, invert=False):
        """Draw rainbow that uniformly distributes itself across all pixels."""
        for j in range(256*iterations):
            for i in range(self.strip.numPixels()):
                index = i
                if invert:
                    index = self.strip.numPixels() - i - 1
                self.strip.setPixelColor(index, self.wheel((int(i * 256 / self.strip.numPixels()) + j) & 255))

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

    def startupAnimation(self, wait_ms=50):
        """Rainbow movie theater light style chaser animation."""
        for j in range(256):
            for q in range(3):
                for i in range(0, self.strip.numPixels(), 3):
                    self.strip.setPixelColor(i+q, self.wheel((i+j) % 255))

                self.strip.show()
                time.sleep(wait_ms/1000.0)

                for i in range(0, self.strip.numPixels(), 3):
                    self.strip.setPixelColor(i+q, 0)

                # Stop animation on connection
                if self.isMpdConnected():
                    return

    def playbackAnimation(self, wait_ms=20, iterations=5, invert=False):
        """Draw rainbow that uniformly distributes itself across all pixels."""
        for j in range(256*iterations):
            for i in range(self.strip.numPixels()):
                index = i
                if invert:
                    index = self.strip.numPixels() - i - 1
                self.strip.setPixelColor(index, self.wheel((int(i * 256 / self.strip.numPixels()) + j) & 255))

            self.strip.show()  
            time.sleep(wait_ms/1000.0)
            if self.is_pressed or self.songChangedThisFrame or self.checkWantsShutdown():
                return

    def loop(self):
        """LED loop"""

        anim_tickrate = 16.6666666/1000.0 # 60fps
        #anim_startup = ColorWipeAnimation(self.strip, 0.5, Color(255, 200, 0))
        anim_startup = FadeAnimation(self.strip, 1.0, Color(0,0,0), Color(255,128,0))
        anim_startup2 = FadeAnimation(self.strip, 0.3, Color(255,128,0), Color(0,0,0))
        anim_theaterchaseRainbow = TheaterChaseRainbowAnimation(self.strip, anim_tickrate * 2)
        anim_fire = FireAnimation(self.strip)
        anim_theaterchase = TheaterChase(self.strip, Color(255, 255, 0), anim_tickrate * 2)
        anim_rainbowCycle = RainbowCycleAnimation(self.strip, 5/1000.0, True)
        anim_rainbow = RaimbowAnimation(self.strip, 5/1000.0)

        anim_shutdown = ColorWipeAnimation(self.strip, 3.0, Color(0,0,0))

        # Fixed tick implementation
        while True:
            #self.isMpdConnected()
            #self.songChangedThisFrame = self.mpdSongChanged()

            #if not anim_startup.isFinished():
            #    anim_startup.tick(anim_tickrate)
            #elif not anim_startup2.isFinished():
            #    anim_startup2.tick(anim_tickrate)
            #else:
            #    anim_startup.reset()
            #    anim_startup2.reset()
            #anim_theaterchase.tick(anim_tickrate)
            anim_rainbow.tick(anim_tickrate)

            # Shutdown
            if self.killMe:
                self.logger.info("Kill")
                self.colorWipeInstant(Color(0,0,0))
                signal.raise_signal(signal.SIGINT) # needed so gpio_control continues exiting
                break
            if self.checkWantsShutdown():
                self.logger.info("Shutdown")                
                self.colorWipe(Color(0,0,0), 10)
                signal.raise_signal(signal.SIGINT) # needed so gpio_control continues exiting
                break

            time.sleep(anim_tickrate)
            continue

            # Waiting for connection
            if not self.mpdConnected:
                self.logger.info("MPD: Waiting for connection")
                # Play wait for animation
                self.mpdHadConnection = False     
                self.startupAnimation(33)
                continue 
            # Connection done, play quick one shot anim
            elif not self.mpdHadConnection:
                self.logger.info("MPD connected/ Started")
                # Play animation once on connection                    
                self.mpdHadConnection = True
                self.theaterChase(Color(255, 255, 0), 16)

            # Pressed = Not playing
            if self.is_pressed:
                self.simulateFire(100)
            # Released = Playing
            else:
                # Card scanned but nothing is playing
                if not self.mpdIsPlaying():
                    self.theaterChase(Color(255,15,4), 33, 1)
                    continue

                # Play quick cycle on song change
                if self.songChangedThisFrame:
                    self.rainbowCycle(0.33, 3, True)
                # Playing
                else:
                    self.playbackAnimation(5, 1, True)
            
            # Ensure inifite loop but also make sure that there is always some sleep time to not
            # kill the cpu although all animations contain a sleep anyways, just to be sure
            time.sleep(anim_tickrate/1000.0)
            self.songChangedThisFrame = False


