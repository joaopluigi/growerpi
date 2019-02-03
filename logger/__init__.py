"""
Logging package for Python 3.5+

It encapsulates the python logging library (https://github.com/python/cpython/blob/master/Lib/logging/__init__.py)
and creates a unique Logger object using the QueueHandler:

> The QueueHandler class supports sending logging messages to a queue, such as
> those implemented in the queue or multiprocessing modules.
>
> Along with the QueueListener class, QueueHandler can be used to let handlers do
> their work on a separate thread from the one which does the logging. This is
> important in Web applications and also other service applications where threads
> servicing clients need to respond as quickly as possible, while any potentially
> slow operations are done on a separate thread
>
> read more at https://docs.python.org/3/library/logging.handlers.html

To use, simply 'import logger' and log away!

NOTE: Configuration can be changed at runtime by updating the 'logging.yml' file
"""

# Log config file location and global logger name
# Change if need
DEFAULTS = {
    'CONFIG_FILE': 'logger/logger.yml',
    'LOGGER_NAME': 'root'
}


from yaml import load
from queue import Queue
from hashlib import md5
from threading import RLock
from logging import FileHandler, Formatter, getLogger
from logging.handlers import QueueHandler, QueueListener


__all__ = [ 'critical', 'error', 'exception', 'warning', 'debug',
            'info', 'log',  'CRITICAL', 'FATAL', 'ERROR', 'WARNING',
            'WARN', 'INFO', 'DEBUG' ]


#---------------------------------------------------------------------------
# Level related stuff
# Default levels and level names, these can be replaced with any positive set
# of values having corresponding names.
#---------------------------------------------------------------------------

CRITICAL = 50
FATAL = CRITICAL
ERROR = 40
WARNING = 30
WARN = WARNING
INFO = 20
DEBUG = 10

_levelToName = {
    CRITICAL: 'CRITICAL',
    ERROR: 'ERROR',
    WARNING: 'WARNING',
    INFO: 'INFO',
    DEBUG: 'DEBUG'
}

#---------------------------------------------------------------------------
# Thread-related stuff
#---------------------------------------------------------------------------

#
# _lock is used to serialize access to shared data structures in this module.
# This needs to be an RLock because _init() creates and configures a global Logger,
# and so might arbitrary user threads.
#

_lock = RLock()

def _acquireLock():
    """
    Acquire the module-level lock for serializing access to shared data.
    This should be released with _releaseLock().
    """
    if _lock:
        _lock.acquire()

def _releaseLock():
    """
    Release the module-level lock acquired by calling _acquireLock().
    """
    if _lock:
        _lock.release()

#---------------------------------------------------------------------------
# Configuration classes and functions
# Intended to be 'private', change at your own risk :P
#---------------------------------------------------------------------------

def _config():
    global logger

    if 'logger' not in globals():
        _init()
    else:
        config = _ConfigFile.getConfig()
        logger.setLevel(config.get('level'))

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
        level = None
        formatter = None
        datefmt = None
        try:
            config = _ConfigFile._open('r', yaml=True)
            level = config['logging'].get('level')
            formatter = config['logging'].get('format')
            datefmt = config['logging'].get('datefmt')
        except:
            level = 'WARNING'
            formatter = '%(asctime)s %(levelname)s %(message)s'
            datefmt = '%Y-%m-%d %H:%M:%S'

        return { 'level': level, 'formatter': formatter, 'datefmt': datefmt }

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

class _LoggerHandler(FileHandler):
    """
    A handler class which inherits from FileHandler. Note that this class
    does not changes how FileHandler emits records, it just add a check
    for logger reconfiguration if config file has changed
    """

    def __init__(self, file):
        FileHandler.__init__(self, file)
        self.configHash = _ConfigFile.md5sum()

    def emit(self, record):
        if self.configHash != _ConfigFile.md5sum():
            _config()
            self.configHash = _ConfigFile.md5sum()

        FileHandler.emit(self, record)

def _init():
    """
    Initiate the logger

    Create a QueueHandler wich will be added together with
    LoggerHandler on a QueueListener. It uses a global logger
    variable so we can know if log has been already initialized.
    Applies configuration from config file.
    """
    _acquireLock()
    try:
        global logger

        # do NOT initialize again
        if 'logger' in globals():
            return

        # Create QueueHandler
        que = Queue(-1) # no limit on size
        queue_handler = QueueHandler(que)

        # Get config parameters
        config = _ConfigFile.getConfig()

        # Set Handler
        handler = _LoggerHandler('logger/logger.log')
        handler.setFormatter(Formatter(config.get('formatter'), config.get('datefmt')))

        # Create Logger
        logger = getLogger(DEFAULTS.get('LOGGER_NAME'))
        logger.addHandler(queue_handler)
        logger.setLevel(config.get('level'))

        # Start listener
        listener = QueueListener(que, handler)
        listener.start()
    finally:
        _releaseLock()

#---------------------------------------------------------------------------
# Utility functions at module level.
# Basically delegate everything to the global logger from logging module.
#---------------------------------------------------------------------------

def critical(msg, *args, **kwargs):
    """
    Log a message with severity 'CRITICAL' on the root logger. If the logger
    has not be initialized yet, do it now.
    """
    global logger
    if 'logger' not in globals():
        _init()

    logger.critical(msg, *args, **kwargs)

def error(msg, *args, **kwargs):
    """
    Log a message with severity 'ERROR' on the root logger. If the logger
    has not be initialized yet, do it now.
    """
    global logger
    if 'logger' not in globals():
        _init()

    logger.error(msg, *args, **kwargs)

def exception(msg, *args, exc_info=True, **kwargs):
    """
    Log a message with severity 'ERROR' on the root logger, with exception
    information. If the logger has not be initialized yet, do it now.
    """
    global logger
    if 'logger' not in globals():
        _init()

    logger.error(msg, *args, exc_info=exc_info, **kwargs)

def warning(msg, *args, **kwargs):
    """
    Log a message with severity 'WARNING' on the root logger. If the logger has
    not be initialized yet, do it now.
    """
    global logger
    if 'logger' not in globals():
        _init()

    logger.warning(msg, *args, **kwargs)

def info(msg, *args, **kwargs):
    """
    Log a message with severity 'INFO' on the root logger. If the logger has
    not be initialized yet, do it now.
    """
    global logger
    if 'logger' not in globals():
        _init()

    logger.info(msg, *args, **kwargs)

def debug(msg, *args, **kwargs):
    """
    Log a message with severity 'DEBUG' on the root logger. If the logger has
    not be initialized yet, do it now.
    """
    global logger
    if 'logger' not in globals():
        _init()

    logger.debug(msg, *args, **kwargs)

def log(level, msg, *args, **kwargs):
    """
    Log 'msg % args' with the integer severity 'level' on the root logger. If
    the logger has not be initialized yet, do it now.

    Adds extra check for level argument.
    """
    global logger
    if 'logger' not in globals():
        _init()

    if level not in _levelToName:
        level = WARNING

    logger.log(level, msg, *args, **kwargs)
