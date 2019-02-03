# Python lib imports
from yaml import load
from time import sleep
from hashlib import md5
from datetime import datetime, timezone
from logging import getLogger, NullHandler

# Raspberry lib
import RPi.GPIO as GPIO


__all__ = [ 'run' ]


# Log config file location
# Change if need
DEFAULTS = {
    'CONFIG_FILE': 'watering/watering.yml',
}


#---------------------------------------------------------------------------
# Configuration classes and functions
# Intended to be 'private', change at your own risk :P
#---------------------------------------------------------------------------

class _ConfigFile:

    @staticmethod
    def _open(mode, yaml):
        """
        Open, parse, as yaml if flagged, and close file
        """
        with open(DEFAULTS.get('CONFIG_FILE'), mode) as configFile:
            if yaml is True:
                return load(configFile)

            return configFile.read()

    @staticmethod
    def getConfig():
        """
        Get configuration from yaml. Set default if we got
        some problem while opening the file

        Return an object { 'config': value, ... }
        """
        gpioMode = None
        watering = {}
        try:
            config = _ConfigFile._open('r', yaml=True)
            gpioMode = (GPIO.BCM, GPIO.BOARD)[config.get('gpioMode') == 'BOARD']
            # Index watering config as { 'startHour': 'pin' }
            for wateringTime in config.get('watering'):
                watering[wateringTime.get('startHour')] = { 'pin': wateringTime.get('pin'), 'timeOn': wateringTime.get('timeOn') }
        except Exception as e:
            gpioMode = GPIO.BOARD
             # Never reach
            watering['-1'] = { 'pin': 8, 'timeOn': 3 }

        return { 'gpioMode': gpioMode, 'watering': watering }

    @staticmethod
    def md5sum():
        """
        Open, close, read file and calculate MD5 on its contents

        Used for checking if the configuration file changed
        """
        hashSum = None
        try:
            # Open as read binary
            config = _ConfigFile._open('rb', yaml=False)

            # pipe contents of the file through
            hashSum = md5(config).hexdigest()
        except:
            hashSum = 'none'

        return hashSum

class _State:

    def __init__(self, name, logger):
        self.name = name
        self.logger = logger

    def construct(self, config):
        self.logger.info('state: %s', self.name)

    def run(self, config):
        assert 0, "run not implemented"

    def next(self, config):
        assert 0, "next not implemented"


class _StateMachine:

    def __init__(self, initialState):
        # Config file settings
        self.config = _ConfigFile.getConfig()
        self.configHash = _ConfigFile.md5sum()

        # State settings
        self.oldState = ''
        self.currentState = initialState
        self.currentState.run(self.config)

    def runAll(self):
        while True:
            # Check if config file changed
            if self.configHash != _ConfigFile.md5sum():
                self.config = _ConfigFile.getConfig()
                self.configHash = _ConfigFile.md5sum()

            # Set next state
            self.currentState = self.currentState.next(self.config)

            # Log state that is about to run
            if self.currentState.name != self.oldState:
                self.currentState.construct(self.config)
                self.oldState = self.currentState.name

            # Run state
            self.currentState.run(self.config)

            # Sleep for 0.1 secs
            sleep(0.1)


class _Idle(_State):

    def run(self, config):
        sleep(1)

    def next(self, config):
        wateringDict = config.get('watering')
        startHour = datetime.now(timezone.utc).hour

        if startHour in wateringDict:
            settings = wateringDict.get(startHour)
            config['actual'] = { 'startHour': startHour, 'pin': settings.get('pin'), 'timeOn': settings.get('timeOn') }

            self.logger.debug('actual config: %s', config['actual'])

            return _Watering.initGPIO

        return _Watering.idle


class _InitGPIO(_State):

    def __init__(self, name, logger):
        # Generic init
        _State.__init__(self, name, logger)

        # Init variables
        self.gpioMode = 0
        self.pin = 0

    def construct(self, config):
        # Do generic construct
        _State.construct(self, config)

        # Fetch variables
        self.gpioMode = config.get('gpioMode')
        self.pin = (config.get('actual')).get('pin')

        self.logger.debug('gpioMode: %s', ('BCM', 'BOARD')[self.gpioMode == GPIO.BOARD])
        self.logger.debug('pin: %s', self.pin)

    def run(self, config):
        # Check GPIO mode
        if GPIO.getmode() != self.gpioMode:
            self.logger.error('GPIO mode mismatch with the one on the configuration file')
            return

        # Setup GPIO pin
        GPIO.setup(self.pin, GPIO.OUT)
        sleep(1)

    def next(self, config):
        # Check if GPIO was initialized correctly
        try:
            GPIO.output(self.pin, 1)
            return _Watering.turnOn
        except:
            return _Watering.initGPIO


class _TurnOn(_State):

    def __init__(self, name, logger):
        # Genereic init
        _State.__init__(self, name, logger)

        # Set variables default
        self.counter = 0
        self.pin = 0
        self.timeOn = 3

    def construct(self, config):
        # Do generic construct
        _State.construct(self, config)

        # Fetch variables
        self.counter = 0
        self.pin = (config.get('actual')).get('pin')
        self.timeOn = (config.get('actual')).get('timeOn')

        self.logger.debug('pin: %s', self.pin)
        self.logger.debug('timeOn: %s', self.timeOn)

    def run(self, config):
        GPIO.output(self.pin, 1)
        sleep(1)
        GPIO.output(self.pin, 0)
        sleep(60)
        self.counter = self.counter + 1

    def next(self, config):
        if self.counter >= self.timeOn:
            return _Watering.turnOff

        return _Watering.turnOn


class _TurnOff(_State):

    def __init__(self, name, logger):
        # Genereic init
        _State.__init__(self, name, logger)

        # Set variables default
        self.pin = 0

    def construct(self, config):
        # Do generic construct
        _State.construct(self, config)

        # Fetch variables
        self.pin = (config.get('actual')).get('pin')

        self.logger.debug('pin: %s', self.pin)

    def run(self, config):
        GPIO.output(self.pin, 0)
        sleep(1)

    def next(self, config):
        # Release PIN
        try:
            GPIO.output(self.pin, 1)
            return _Watering.waiting
        except:
            return _Watering.turnOff


class _Waiting(_State):

    def __init__(self, name, logger):
        # Genereic init
        _State.__init__(self, name, logger)

        # Set variables default
        self.startHour = None

    def construct(self, config):
        # Do generic construct
        _State.construct(self, config)

        # Fetch variables
        self.startHour = (config.get('actual')).get('startHour')

        self.logger.debug('startHour: %s', self.startHour)

    def run(self, config):
        sleep(1)

    def next(self, config):
        if self.startHour != datetime.now(timezone.utc).hour:
                return _Watering.idle

        return _Watering.waiting


class _Watering(_StateMachine):

    def __init__(self):
        _StateMachine.__init__(self, _Watering.idle)


def run(logger=None):

    # Add null logger handler if None
    if logger is None:
        logger = getLogger('NullHandlerLogger').addHandler(NullHandler())

    try:
        _Watering.idle = _Idle('Idle', logger)
        _Watering.initGPIO = _InitGPIO('InitGPIO', logger)
        _Watering.turnOn = _TurnOn('TurnOn', logger)
        _Watering.turnOff = _TurnOff('TurnOff', logger)
        _Watering.waiting = _Waiting('Waiting', logger)
        _Watering().runAll()

    except Exception as e:
        logger.exception(e)
