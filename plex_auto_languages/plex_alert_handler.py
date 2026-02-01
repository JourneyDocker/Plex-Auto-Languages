from __future__ import annotations
from typing import TYPE_CHECKING
from time import sleep
import http.client
from queue import Queue, Empty
from threading import Thread, Event
from requests.exceptions import ReadTimeout, ConnectionError
from urllib3.exceptions import ReadTimeoutError, ProtocolError
from plex_auto_languages.alerts import PlexActivity, PlexTimeline, PlexPlaying, PlexStatus
from plex_auto_languages.utils.logger import get_logger

if TYPE_CHECKING:
    from plex_auto_languages.plex_server import PlexServer


logger = get_logger()


class PlexAlertHandler():
    """
    Handles and processes Plex alerts from various notification types.

    This class manages the reception, queuing, and processing of different types of
    Plex alerts including play events, library scans, and activity notifications.
    It runs a background thread to process alerts asynchronously.

    Attributes:
        _plex (PlexServer): Reference to the Plex server instance.
        _trigger_on_play (bool): Whether to process play events.
        _trigger_on_scan (bool): Whether to process scan events.
        _trigger_on_activity (bool): Whether to process activity events.
        _alerts_queue (Queue): Queue for storing alerts to be processed.
        _stop_event (Event): Threading event to signal thread termination.
        _processor_thread (Thread): Background thread for processing alerts.
    """

    def __init__(self, plex: PlexServer, trigger_on_play: bool, trigger_on_scan: bool, trigger_on_activity: bool):
        """
        Initialize the Plex alert handler with specified trigger settings.

        Args:
            plex (PlexServer): The Plex server instance to interact with.
            trigger_on_play (bool): Whether to trigger on play events.
            trigger_on_scan (bool): Whether to trigger on scan events.
            trigger_on_activity (bool): Whether to trigger on activity events.
        """
        self._plex = plex
        self._trigger_on_play = trigger_on_play
        self._trigger_on_scan = trigger_on_scan
        self._trigger_on_activity = trigger_on_activity
        self._alerts_queue = Queue()
        self._stop_event = Event()
        self._processor_thread = Thread(target=self._process_alerts)
        self._processor_thread.daemon = True
        self._processor_thread.start()

    def stop(self) -> None:
        """
        Stop the alert processing thread gracefully.

        Sets the stop event and waits for the processor thread to terminate.
        """
        self._stop_event.set()
        self._processor_thread.join()

    def __call__(self, message: dict) -> None:
        """
        Process incoming Plex alert messages and queue them for handling.

        This method is called when a new Plex alert is received. It determines
        the type of alert, creates the appropriate alert object, and adds it
        to the processing queue.

        Args:
            message (dict): The alert message from Plex server.
        """
        alert_class = None
        alert_field = None
        if self._trigger_on_play and message["type"] == "playing":
            alert_class = PlexPlaying
            alert_field = "PlaySessionStateNotification"
        elif self._trigger_on_activity and message["type"] == "activity":
            alert_class = PlexActivity
            alert_field = "ActivityNotification"
        elif self._trigger_on_scan and message["type"] == "timeline":
            alert_class = PlexTimeline
            alert_field = "TimelineEntry"
        elif self._trigger_on_scan and message["type"] == "status":
            alert_class = PlexStatus
            alert_field = "StatusNotification"

        if alert_class is None or alert_field is None or alert_field not in message:
            return

        for alert_message in message[alert_field]:
            alert = alert_class(alert_message)
            self._alerts_queue.put(alert)

    def _process_alerts(self) -> None:
        """
        Background thread method that processes queued alerts.

        Continuously monitors the alert queue and processes each alert.
        Handles timeouts with retries and logs exceptions.
        This method runs until the stop event is set.
        """
        logger.debug("Starting alert processing thread")
        retry_counter = 0
        while not self._stop_event.is_set():
            try:
                if retry_counter == 0:
                    alert = self._alerts_queue.get(True, 1)
                try:
                    alert.process(self._plex)
                    retry_counter = 0
                except (ReadTimeout, ReadTimeoutError):
                    retry_counter += 1
                    logger.warning(f"ReadTimeout while processing {alert.TYPE} alert, retrying (attempt {retry_counter})...")
                    logger.debug(alert.message)
                    sleep(1)
                # Catch ConnectionError (Requests wrapper) along with low-level ProtocolErrors
                except (http.client.RemoteDisconnected, ProtocolError, ConnectionError) as e:
                    logger.warning(f"[Network] Connection lost while processing {alert.TYPE} alert ({type(e).__name__}). Skipping alert...")
                    logger.debug(f"Alert details: {alert.message}")
                    retry_counter = 0
                except Exception:
                    logger.exception(f"Unable to process {alert.TYPE}")
                    logger.debug(alert.message)
                    retry_counter = 0
            except Empty:
                pass
        logger.debug("Stopping alert processing thread")
