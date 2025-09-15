import time
from typing import Callable
from threading import Thread, Event
import schedule

from plex_auto_languages.utils.logger import get_logger


logger = get_logger()


class Scheduler(Thread):
    """
    A threaded scheduler that executes a callback function at a specified time each day.

    This class extends Thread to run the scheduler in the background, allowing
    the application to perform other tasks while waiting for scheduled events.
    The scheduler can be gracefully shut down when needed.

    Attributes:
        _stop_event (Event): Threading event used to signal the scheduler to stop.
    """

    def __init__(self, time_of_day: str, callback: Callable):
        """
        Initialize the scheduler with a daily task.

        Args:
            time_of_day (str): The time of day to run the callback in 'HH:MM' format.
            callback (Callable): The function to execute at the specified time.
        """
        super().__init__()
        schedule.every().day.at(time_of_day).do(callback)
        self._stop_event = Event()

    def run(self) -> None:
        """
        Start the scheduler loop.

        This method is called when the thread is started. It continuously checks
        for pending scheduled tasks and runs them when due, until shutdown is called.

        Returns:
            None
        """
        logger.info("Starting scheduler")
        while not self._stop_event.is_set():
            schedule.run_pending()
            time.sleep(5)

    def shutdown(self) -> None:
        """
        Gracefully stop the scheduler.

        Sets the stop event flag to signal the scheduler loop to terminate.

        Returns:
            None
        """
        logger.info("Stopping scheduler")
        schedule.clear()
        self._stop_event.set()
