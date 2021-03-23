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
        self.waitForFinish = False
        self.duration = -1
        self.timer = 0
        self.name = ""

    def reset(self):
        self.currentTime = 0.0
        self.timer = 0

    def tick(self, deltaTime):
        self.deltaTime = deltaTime
        self.currentTime += self.deltaTime
        self.timer += self.deltaTime

    def isFinished(self):
        return self.duration < 0 or self.currentTime > self.duration

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

    def __init__(self, strip, duration):          
        super().__init__(strip)
        self.duration = duration
        self.alpha = 0.0
        self.loop = False      
        self.name = "LEDRingAnimationTimed"

    def reset(self):
        super().reset()
        self.alpha = 0.0

    def tick(self, deltaTime):
        if self.loop and self.isFinished():
            self.currentTime = 0.0

        super().tick(deltaTime)
        self.alpha = clamp01(self.currentTime / self.duration)

class FadeAnimation(LEDRingAnimationTimed):
    """ Fade from start to end color in duration """

    def __init__(self, strip, duration, starColor, endColor):             
        super().__init__(strip, duration)
        self.startColor = starColor
        self.endColor = endColor  
        self.name = "FadeAnimation"

    def tick(self, deltaTime):
        super().tick(deltaTime)
        color = lerp.colorRGB(self.startColor, self.endColor, self.alpha)

        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, color)

        self.strip.show()

class ColorWipeAnimation(LEDRingAnimationTimed):
    """ Wipe color across display a pixel at a time """

    def __init__(self, strip, duration, endColor):               
        super().__init__(strip, duration)
        self.endColor = endColor        
        self.timeBetweenPixels = duration / strip.numPixels()
        self.currentPixel = 0
        self.currentPixelShowTime = 0.0 
        self.name = "ColorWipeAnimation"

    def reset(self):
        super().reset()
        self.currentPixel = 0        

    def tick(self, deltaTime):
        super().tick(deltaTime)        

        if self.timer < self.timeBetweenPixels:
            return
        self.timer = 0.0

        self.strip.setPixelColor(self.currentPixel, self.endColor)
        self.strip.show()
        self.currentPixel += 1

class TheaterChase(LEDRingAnimation):
    """Movie theater light style chaser animation."""

    def __init__(self, strip, color, delay=0.01, iterations=1):            
        super().__init__(strip)
        self.color = color
        self.delay = delay
        self.iterations = iterations
        self.j = 0
        self.q = 0    
        self.name = "TheaterChase"

    def reset(self):
        self.j = 0
        self.q = 0
        super().reset()

    def tick(self, deltaTime):
        super().tick(deltaTime)

        if self.timer < self.delay:
            return

        self.timer = 0

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

    def __init__(self, strip, delay = 0.01):             
        super().__init__(strip)
        self.delay = delay
        self.j = 0
        self.q = 0  
        self.name = "TheaterChaseRainbowAnimation"

    def reset(self):
        super().reset()
        self.j = 0
        self.q = 0
       
    def tick(self, deltaTime):
        super().tick(deltaTime)

        if self.timer < self.delay:
            return

        self.timer = 0

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
        super().__init__(strip)
        self.delay = delay
        self.iter = 0
        self.name = "RaimbowAnimation"

    def reset(self):
        self.iter = 0
        super().reset()

    def tick(self, deltaTime):
        super().tick(deltaTime)

        if self.timer < self.delay:
            return

        self.timer = 0
        
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, self.posToRainbow((i + self.iter) & 255))

        self.strip.show()
        self.iter += 1

class RainbowCycleAnimation(LEDRingAnimation):
    """Draw rainbow that uniformly distributes itself across all pixels."""
    def __init__(self, strip, delay = 0.01, invert = False):        
        super().__init__(strip)
        self.delay = delay
        self.invert = invert
        self.iter = 0
        self.name = "RainbowCycleAnimation"

    def reset(self):
        super().reset()
        self.iter = 0        

    def tick(self, deltaTime):
        super().tick(deltaTime)

        if self.timer < self.delay:
            return

        self.timer = 0
        
        for i in range(self.strip.numPixels()):
            index = i
            if self.invert:
                index = self.strip.numPixels() - i - 1
            self.strip.setPixelColor(index, self.posToRainbow((int(i * 256 / self.strip.numPixels()) + self.iter) & 255))

        self.strip.show()
        self.iter += 1
        
class FireAnimation(LEDRingAnimation):    
    """Simulates fire according to https://www.az-delivery.de/en/blogs/azdelivery-blog-fur-arduino-und-raspberry-pi/eine-stimmungslaterne"""

    def __init__(self, strip, intervalMin = 0.05, intervalMax = 0.15):        
        super().__init__(strip)
        self.intervalMin = intervalMin
        self.intervalMax = intervalMax
        self.randomizeInterval()
        self.newLightValue = [0] * ((strip.numPixels() * 3) + 3)
        self.currentPixelToUpdate = 0
        self.randomizeNewFireColors()
        self.name = "FireAnimation"

    def reset(self):
        self.currentPixelToUpdate = 0
        self.randomizeInterval()
        self.newLightValue = [0] * ((self.strip.numPixels() * 3) + 3)
        self.randomizeNewFireColors()
        super().reset()

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

        if self.timer < self.fireInterval:            
            return

        self.randomizeInterval()
        self.timer = 0.0

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
    """ LED ring implementation wrapping a button to access the RFID gpio input """

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
        self.colorWipeInstant(Color(0,0,0))

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

        return self.mpc.status()["state"] == "play"

    def colorWipeInstant(self, color):
        """Wipe color across display all pixels."""
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, color)            
        
        self.strip.show()

    def loop(self):
        """LED loop"""

        anim_fps = 144.0
        anim_tickrate = (1.0/anim_fps)
        currentAnimation = None
        nextAnimation = None
               
        # Setup animations
        anim_startup = FadeAnimation(self.strip, 0.05, Color(0,0,0), Color(255,128,0))
        anim_startup.waitForFinish = True
        anim_startup2 = FadeAnimation(self.strip, 0.5, Color(255,128,0), Color(0,0,0))
        anim_startup2.waitForFinish = True
        anim_shutdown = ColorWipeAnimation(self.strip, 3.0 / LED_COUNT, Color(0,0,0))
        anim_mpdConnected = ColorWipeAnimation(self.strip, 1, Color(255, 255, 128))
        anim_mpdConnected.waitForFinish = True
        anim_waitForInput = FireAnimation(self.strip)
        anim_inputError = TheaterChase(self.strip, Color(255, 32, 0), 1/90.0)
        #anim_nextSong = RainbowCycleAnimation(self.strip, anim_tickrate * 5, True)
        #anim_nextSong.duration = 0.5
        anim_nextSong = ColorWipeAnimation(self.strip, 0.33, Color(255, 128, 0))        
        anim_nextSong.name = "NextSongAnimation"
        anim_nextSong.waitForFinish = True  
        anim_playingSong = RainbowCycleAnimation(self.strip, 1/72, True)

        # Fixed tick implementation
        while True:
            wait = False
            if nextAnimation is not None:
                if currentAnimation is not None:
                    if currentAnimation.waitForFinish and not currentAnimation.isFinished():
                        wait = True                

                if not wait and currentAnimation is not nextAnimation:
                    self.logger.info("NEW animation: " + nextAnimation.name)
                    currentAnimation = nextAnimation

            if currentAnimation is not None:
                currentAnimation.tick(anim_tickrate)
                if currentAnimation.waitForFinish:
                    self.logger.info("Waiting for finish " + str(currentAnimation.currentTime) + "/" + str(currentAnimation.duration))

            time.sleep(anim_tickrate)
            
            # Shutdown
            if self.killMe:
                self.logger.info("Kill")
                self.colorWipeInstant(Color(0,0,0))
                nextAnimation = None
                signal.raise_signal(signal.SIGINT) # needed so gpio_control continues exiting
                break
            if self.checkWantsShutdown():
                self.logger.info("Shutdown")
                nextAnimation = anim_shutdown
                if anim_shutdown.isFinished():
                    signal.raise_signal(signal.SIGINT) # needed so gpio_control continues exiting
                continue

            # Wait for an animation to get finished 
            if wait:
                self.logger.info("Waiting for animation")
                continue

            self.isMpdConnected()
            self.songChangedThisFrame = self.mpdSongChanged()

            # Waiting for connection
            if not self.mpdConnected:
                self.logger.info("MPD: Waiting for connection")
                # Play wait for animation
                self.mpdHadConnection = False
                if not anim_startup.isFinished():
                    nextAnimation = anim_startup
                elif not anim_startup2.isFinished():
                    nextAnimation = anim_startup2
                continue 
            # Connection done, play quick one shot anim
            elif not self.mpdHadConnection:
                self.logger.info("MPD connected/ Started")
                # Play animation once on connection                    
                self.mpdHadConnection = True
                nextAnimation = anim_mpdConnected

            # Pressed = Not playing
            if self.is_pressed:
                nextAnimation = anim_waitForInput                
            # Released = Playing
            else:
                # Card scanned but nothing is playing
                if not self.mpdIsPlaying():
                    nextAnimation = anim_inputError
                    continue

                # Play quick cycle on song change
                if self.songChangedThisFrame:
                    anim_nextSong.reset()
                    nextAnimation = anim_nextSong
                # Playing
                else:
                    nextAnimation = anim_playingSong
           
            self.songChangedThisFrame = False


