import time
from typing import Callable
from threading import Thread, Event
import schedule

from plex_auto_languages.utils.logger import get_logger


logger = get_logger()


VALID_DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}


class Scheduler(Thread):
    """
    A threaded scheduler that executes a callback at a scheduled time,
    optionally restricted to specific days of the week.

    Extends Thread to run in the background. Can be gracefully shut down.

    Attributes:
        _stop_event (Event): Threading event used to signal the scheduler to stop.
    """

    def __init__(self, time_of_day: str, callback: Callable, schedule_days: list = None):
        """
        Initialize the scheduler.

        Args:
            time_of_day (str): Time to run the callback in 'HH:MM' format.
            callback (Callable): Function to execute at the scheduled time.
            schedule_days (list, optional): Days to run on (lowercase English).
                When empty or None, runs every day.
        """
        super().__init__()
        days = schedule_days or []
        if days:
            for day in days:
                getattr(schedule.every(), day).at(time_of_day).do(callback)
        else:
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
