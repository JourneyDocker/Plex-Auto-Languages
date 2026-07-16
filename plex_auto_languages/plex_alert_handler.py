from __future__ import annotations
from typing import TYPE_CHECKING
from time import sleep, monotonic
import http.client
from queue import Queue, Empty, Full
from threading import Thread, Event
import concurrent.futures
from requests.exceptions import ReadTimeout, ConnectionError, HTTPError, RequestException
from urllib3.exceptions import ReadTimeoutError, ProtocolError
from plex_auto_languages.alerts import PlexActivity, PlexTimeline, PlexPlaying, PlexStatus
from plex_auto_languages.utils.logger import get_logger

if TYPE_CHECKING:
    from plex_auto_languages.plex_server import PlexServer


logger = get_logger()

# A single item can re-emit the same timeline event many times per second while Plex
# regenerates its preview thumbnails / analysis; collapsing repeats of the same dedupe_key
# within this window keeps one item from flooding the queue. Short enough that legitimately
# distinct changes are never suppressed (process() re-fetches current state and the cache
# guards against reprocessing anyway).
DEDUPE_WINDOW_SECONDS = 5.0

# Number of worker threads draining the alert queue. The producer (plexapi
# AlertListener callback) enqueues alerts on its own thread; a single consumer
# serializes behind each alert's network I/O (fetch_item -> reload -> fan-out to
# all users), which is what lets the bounded queue fill on a large/busy library.
# A small pool drains concurrently so the queue stays near zero. Kept modest:
# each worker does real Plex I/O, so this is I/O-bound, not CPU-bound, and the
# per-episode user fan-out already parallelizes within process().
CONSUMER_WORKERS = 4


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
        _processor_threads (list[Thread]): Worker threads draining the queue.
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
        # Bounded so a consumer that cannot keep up with Plex's notification
        # rate can never accumulate alerts without limit. The pre-filter in
        # __call__ keeps the steady-state depth near zero; this is the hard cap.
        self._alerts_queue = Queue(maxsize=10000)
        # Single-producer (AlertListener) counter; the stats thread only reads it.
        self._dropped_alerts = 0
        # Producer-thread-only dedup state: collapse a rapid burst of identical alerts
        # (same dedupe_key seen within the window) so one misbehaving item cannot flood
        # the queue. Only the single AlertListener thread touches it, so no lock needed.
        self._recent_keys = {}
        self._deduped_alerts = 0
        self._dedupe_window = DEDUPE_WINDOW_SECONDS
        self._stop_event = Event()
        # Pool of consumer threads. Each pulls from the shared queue; the queue's
        # internal lock serializes get()/task_done() so no extra coordination needed.
        self._processor_threads = [
            Thread(target=self._process_alerts, name=f"alert-consumer-{worker_index}")
            for worker_index in range(CONSUMER_WORKERS)
        ]
        for consumer_thread in self._processor_threads:
            consumer_thread.daemon = True
            consumer_thread.start()
        # Log queue health (depth + total drops) every 5 minutes so the bound is
        # observable from the container logs without a heap inspection.
        self._stats_thread = Thread(target=self._log_queue_stats)
        self._stats_thread.daemon = True
        self._stats_thread.start()

    def _log_queue_stats(self) -> None:
        """
        Periodic queue-health log (every 5 min). Under the pre-filter the depth
        should stay near zero; a rising depth or any dropped alerts means the
        consumer pool cannot keep up with Plex's alert rate. Read-only on
        shared state; exits promptly when stopped.
        """
        while not self._stop_event.wait(300):
            logger.info(
                "Alert queue depth=%d/%d dropped_total=%d deduped_total=%d"
                % (self._alerts_queue.qsize(), self._alerts_queue.maxsize,
                   self._dropped_alerts, self._deduped_alerts))

    def _is_duplicate(self, alert) -> bool:
        """Return True if this alert repeats a dedupe_key already seen within the window
        (a fixed, non-sliding window: the key is re-armed on the first event after each
        window expires, so a sustained flood still re-enqueues the item once per window
        and never starves real reprocessing). Runs only on the producer thread."""
        key = alert.dedupe_key(self._plex)
        if key is None:
            return False
        now = monotonic()
        last = self._recent_keys.get(key)
        if last is not None and (now - last) < self._dedupe_window:
            self._deduped_alerts += 1
            return True
        self._recent_keys[key] = now
        if len(self._recent_keys) > 2048:
            self._prune_recent_keys(now)
        return False

    def _prune_recent_keys(self, now: float) -> None:
        """Drop expired dedup entries so the map stays bounded under a burst of many
        distinct items (e.g. a large library import)."""
        cutoff = now - self._dedupe_window
        self._recent_keys = {k: t for k, t in self._recent_keys.items() if t >= cutoff}

    def stop(self) -> None:
        """
        Stop the alert processing threads gracefully.

        Sets the stop event and waits for the processor threads to terminate.
        """
        self._stop_event.set()
        for consumer_thread in self._processor_threads:
            consumer_thread.join()

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
            # Drop alerts whose process() is a pure no-op (side-effect-free,
            # network-free early-return) before they ever reach the queue. This
            # is what stops the unbounded timeline-notification accumulation at
            # the source. Only PlexTimeline overrides is_relevant; playing /
            # activity / status inherit the default (True) so their cache side
            # effects are preserved.
            if not alert.is_relevant(self._plex):
                continue
            # Collapse a rapid burst of identical alerts (one item re-emitting the same
            # event many times per second) before it can flood the bounded queue.
            if self._is_duplicate(alert):
                continue
            # Never block the producer (the plexapi AlertListener callback
            # thread): if the consumer is so far behind the bounded queue is
            # full, drop and count rather than stall the websocket reader.
            try:
                self._alerts_queue.put_nowait(alert)
            except Full:
                self._dropped_alerts += 1
                if self._dropped_alerts % 1000 == 1:
                    logger.warning(
                        "Alert queue full (maxsize=%d); dropped %d alert(s) so "
                        "far - the consumer thread is not keeping up with Plex "
                        "notifications." % (self._alerts_queue.maxsize, self._dropped_alerts))

    def _process_alerts(self) -> None:
        """
        Consumer thread method that processes queued alerts.

        Runs in one of several worker threads (see CONSUMER_WORKERS). Each worker
        pulls alerts from the shared queue and processes them. The retry counter is
        thread-local so a slow/retrying alert in one worker cannot bleed its state
        into another worker. Handles timeouts with retries and logs exceptions.
        Runs until the stop event is set.
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
                    if retry_counter > 3:
                        logger.error(f"ReadTimeout persisted for {alert.TYPE} alert. Skipping.")
                        retry_counter = 0
                        continue
                    logger.warning(f"ReadTimeout while processing {alert.TYPE} alert, retrying (attempt {retry_counter})...")
                    sleep(1)
                except (http.client.RemoteDisconnected, ProtocolError, ConnectionError, HTTPError) as e:
                    logger.warning(f"[Network] {type(e).__name__} while processing {alert.TYPE} alert. Skipping...")
                    logger.debug(f"Error details: {e}")
                    retry_counter = 0
                except RequestException as e:
                    logger.error(f"[Requests] General failure while processing {alert.TYPE}: {e}")
                    retry_counter = 0
                except Exception:
                    logger.exception(f"Unexpected error while processing {alert.TYPE}")
                    logger.debug(alert.message)
                    retry_counter = 0
            except Empty:
                pass
        logger.debug("Stopping alert processing thread")
