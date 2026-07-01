import time
from typing import Callable, List, Optional
from threading import Thread, Event
import schedule

from plex_auto_languages.utils.logger import get_logger


logger = get_logger()


class Scheduler(Thread):
    """
    A threaded scheduler that executes a callback function at a specified time.

    If no schedule days are provided, the callback runs every day.
    If schedule days are provided, the callback runs only on those days.
    """

    VALID_DAYS = {
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    }

    def __init__(self, time_of_day: str, callback: Callable, days: Optional[List[str]] = None):
        """
        Initialize the scheduler.

        Args:
            time_of_day (str): The time of day to run the callback in 'HH:MM' format.
            callback (Callable): The function to execute at the specified time.
            days (Optional[List[str]]): Days on which the callback should run.
                Empty or None means every day.
        """
        super().__init__()
        self._stop_event = Event()

        normalized_days = [
            day.strip().lower()
            for day in (days or [])
            if isinstance(day, str) and day.strip()
        ]

        if len(normalized_days) == 0:
            schedule.every().day.at(time_of_day).do(callback)
            logger.info(f"Scheduler configured to run every day at {time_of_day}")
            return

        for day in normalized_days:
            if day not in self.VALID_DAYS:
                raise ValueError(f"Invalid scheduler day: {day}")

            getattr(schedule.every(), day).at(time_of_day).do(callback)

        logger.info(f"Scheduler configured to run on {', '.join(normalized_days)} at {time_of_day}")

    def run(self) -> None:
        """
        Start the scheduler loop.
        """
        logger.info("Starting scheduler")
        while not self._stop_event.is_set():
            schedule.run_pending()
            time.sleep(5)

    def shutdown(self) -> None:
        """
        Gracefully stop the scheduler.
        """
        logger.info("Stopping scheduler")
        schedule.clear()
        self._stop_event.set()