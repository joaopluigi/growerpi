import logger
import watering
from time import sleep
from threading import Thread

# Raspberry lib
import RPi.GPIO as GPIO


if __name__ == "__main__":

    try:
        GPIO.setmode(GPIO.BOARD)

        wateringThread = Thread(target=watering.run(logger=logger))
        wateringThread.daemon = True
        wateringThread.start()

        while True:
            sleep(0.1)

    except Exception as e:
        GPIO.cleanup()
        logger.exception(e)
