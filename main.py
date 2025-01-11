import signal
import argparse
from time import sleep
from websocket import WebSocketConnectionClosedException

from plex_auto_languages.plex_server import PlexServer
from plex_auto_languages.utils.notifier import Notifier
from plex_auto_languages.utils.logger import init_logger
from plex_auto_languages.utils.scheduler import Scheduler
from plex_auto_languages.utils.configuration import Configuration
from plex_auto_languages.utils.healthcheck import HealthcheckServer

# Version information
__version__ = "1.3.2-dev3"

class PlexAutoLanguages:
    """
    The main class that orchestrates the functionality of Plex Auto Languages.

    Handles configuration, health checks, notifications, scheduling, and interactions with the Plex server.
    """

    def __init__(self, user_config_path: str):
        """
        Initialize the application with user configuration.

        :param user_config_path: Path to the user configuration file.
        """
        self.alive = False  # Indicates whether the application is active and running.
        self.must_stop = False  # Flags if the application should stop the current iteration.
        self.stop_signal = False  # Flags if a stop signal (e.g., SIGINT) was received.
        self.plex_alert_listener = None  # Listener for Plex server alerts.
        self.initializing = False

        # Load the configuration file.
        self.config = Configuration(user_config_path)

        # Initialize the health-check server.
        self.healthcheck_server = HealthcheckServer(
            "Plex-Auto-Languages", self.is_ready, self.is_healthy
        )
        self.healthcheck_server.start()

        # Initialize the notifier for sending alerts, if enabled.
        self.notifier = None
        if self.config.get("notifications.enable"):
            self.notifier = Notifier(self.config.get("notifications.apprise_configs"))

        # Initialize the scheduler for periodic tasks, if enabled.
        self.scheduler = None
        if self.config.get("scheduler.enable"):
            self.scheduler = Scheduler(
                self.config.get("scheduler.schedule_time"), self.scheduler_callback
            )

        # Placeholder for Plex server interactions.
        self.plex = None

        # Set up signal handlers for graceful termination.
        self.set_signal_handlers()

    def init(self):
        """
        Initialize the connection to the Plex server using the configured URL and token.
        """
        self.plex = PlexServer(
            self.config.get("plex.url"),
            self.config.get("plex.token"),
            self.notifier,
            self.config
        )

    def is_ready(self):
        """
        Check if the application is ready to handle requests.
        The application is considered ready if the Plex server has been initialized.

        :return: True if the application is ready, False otherwise.
        """
        if self.initializing:
            return True
        if not self.plex:
            logger.warning("Plex server is not initialized yet.")
            return False
        return self.alive

    def is_healthy(self):
        """
        Check the health of the application. This includes verifying the status of the Plex server.
        Now considers initialization state to prevent premature health check failures.

        :return: True if the application and Plex server are healthy, False otherwise.
        """
        if self.initializing:
            logger.debug("Application is currently initializing")
            return True
        if not self.alive:
            logger.warning("Application is not alive.")
            return False
        if not self.plex:
            logger.warning("Plex server is not initialized yet.")
            return False
        if not self.plex.is_alive:
            logger.warning("Plex server is not alive.")
            return False
        return True

    def set_signal_handlers(self):
        """
        Set up handlers for SIGINT and SIGTERM signals to allow graceful shutdown.
        """
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

    def stop(self, *_):
        """
        Handle termination signals (SIGINT or SIGTERM) by flagging the application to stop gracefully.
        """
        logger.info("Received SIGINT or SIGTERM, stopping gracefully")
        self.must_stop = True
        self.stop_signal = True

    def start(self):
        """
        Start the main loop of the application, with improved initialization handling.
        """
        if self.scheduler:
            self.scheduler.start()

        while not self.stop_signal:
            self.must_stop = False
            self.initializing = True  # Set initializing flag
            logger.info("Starting initialization phase")
            try:
                self.init()
                if self.plex is None:
                    logger.error("Failed to initialize Plex server")
                    break

                # Start listening for alerts from the Plex server.
                self.plex.start_alert_listener(self.alert_listener_error_callback)
                self.alive = True
                logger.info("Initialization completed successfully")
            except Exception as e:
                logger.error(f"Error during initialization: {str(e)}")
                raise
            finally:
                self.initializing = False  # Clear initializing flag

            count = 0  # Counter for periodic health checks
            while not self.must_stop:
                sleep(1)
                count += 1
                if count % 60 == 0 and not self.plex.is_alive:
                    logger.warning("Lost connection to the Plex server")
                    self.must_stop = True

            # Clean up when stopping
            self.alive = False
            self.plex.save_cache()
            self.plex.stop()
            if not self.stop_signal:
                sleep(1)
                logger.info("Trying to restore the connection to the Plex server...")

        if self.scheduler:
            self.scheduler.shutdown()
            self.scheduler.join()

        # Shut down the health-check server
        self.healthcheck_server.shutdown()

    def alert_listener_error_callback(self, error: Exception):
        """
        Handle errors that occur in the Plex server alert listener.

        :param error: The exception that occurred.
        """
        if isinstance(error, WebSocketConnectionClosedException):
            logger.warning("The Plex server closed the websocket connection")
        elif isinstance(error, UnicodeDecodeError):
            logger.debug("Ignoring a websocket payload that could not be decoded")
            return
        else:
            logger.error("Alert listener had an unexpected error")
            logger.error(error, exc_info=True)
        self.must_stop = True

    def scheduler_callback(self):
        """
        Callback function for scheduled tasks.
        Performs a deep analysis if the Plex server is alive.
        """
        if self.plex is None or not self.plex.is_alive:
            return
        logger.info("Starting scheduler task")
        self.plex.start_deep_analysis()

if __name__ == "__main__":
    # Initialize the logger.
    logger = init_logger()

    # Log the version information.
    logger.info(f"Starting Plex Auto Languages - Version {__version__}")

    # Parse command-line arguments.
    parser = argparse.ArgumentParser(description="Plex Auto Languages")
    parser.add_argument("-c", "--config_file", type=str, help="Path to the configuration file")
    args = parser.parse_args()

    # Create the main application instance.
    plex_auto_languages = PlexAutoLanguages(args.config_file)

    # Start the application.
    plex_auto_languages.start()
