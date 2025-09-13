import signal
import argparse
from time import sleep
from websocket import WebSocketConnectionClosedException, WebSocketTimeoutException

from plex_auto_languages.plex_server import PlexServer
from plex_auto_languages.utils.notifier import Notifier
from plex_auto_languages.utils.logger import init_logger
from plex_auto_languages.utils.scheduler import Scheduler
from plex_auto_languages.utils.configuration import Configuration
from plex_auto_languages.utils.healthcheck import HealthcheckServer

# Version information
__version__ = "1.3.11"

class PlexAutoLanguages:
    """
    The main class that orchestrates the functionality of Plex Auto Languages.

    This class serves as the central coordinator for the application, managing the lifecycle
    of various components and handling the core application logic. It is responsible for:

    - Loading and managing configuration settings
    - Setting up health checks to monitor application status
    - Configuring notification services for alerts
    - Scheduling periodic tasks for maintenance operations
    - Establishing and maintaining connection to the Plex server
    - Handling graceful startup and shutdown procedures
    - Processing signals for proper application termination

    The class implements a robust error handling mechanism and automatic reconnection
    to ensure continuous operation even in case of temporary connection issues.

    Attributes:
        alive (bool): Indicates whether the application is active and running.
        must_stop (bool): Flags if the application should stop the current iteration.
        stop_signal (bool): Flags if a stop signal (e.g., SIGINT) was received.
        plex_alert_listener (PlexAlertListener): Listener for Plex server alerts.
        initializing (bool): Indicates if the application is in initialization phase.
        config (Configuration): Configuration object containing application settings.
        healthcheck_server (HealthcheckServer): Server for monitoring application health.
        notifier (Notifier): Service for sending notifications and alerts.
        scheduler (Scheduler): Component for scheduling periodic tasks.
        plex (PlexServer): Interface for interacting with the Plex Media Server.
    """

    def __init__(self, user_config_path: str):
        """
        Initialize the application with user configuration.

        This constructor sets up all necessary components and prepares the application
        for execution, but does not start any active processes until the start() method
        is called.

        Args:
            user_config_path (str): Path to the YAML configuration file containing
                all settings for the application.

        Note:
            The configuration file must contain valid settings for at least the
            Plex server URL and token.
        """
        self.alive = False
        self.must_stop = False
        self.stop_signal = False
        self.plex_alert_listener = None
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

        This method establishes a connection to the Plex server using the credentials
        provided in the configuration. It creates a new PlexServer instance that will
        be used for all subsequent interactions with the Plex Media Server.

        If the connection fails, the method will raise an exception that will be caught
        by the start() method.

        Returns:
            None

        Raises:
            Exception: If connection to the Plex server fails.
        """
        self.plex = PlexServer(
            self.config.get("plex.url"),
            self.config.get("plex.token"),
            self.notifier,
            self.config
        )

    def is_ready(self) -> bool:
        """
        Check if the application is ready to handle requests.

        The application is considered ready if either:
        1. It is currently in the initialization phase, or
        2. The Plex server has been successfully initialized and the application is alive.

        This method is used by the health check server to determine if the application
        can accept and process requests.

        Returns:
            bool: True if the application is ready to handle requests, False otherwise.
        """
        if self.initializing:
            return True
        if not self.plex:
            logger.warning("Plex server is not initialized yet")
            return False
        return self.alive

    def is_healthy(self) -> bool:
        """
        Check the health of the application.

        This method performs a comprehensive health check of the application by verifying:
        1. If the application is in initialization phase (considered healthy)
        2. If the application is marked as alive
        3. If the Plex server has been initialized
        4. If the connection to the Plex server is active

        This method is used by the health check server to monitor the overall health
        of the application and detect any issues that might require attention.

        Returns:
            bool: True if the application and all its components are healthy, False otherwise.
        """
        if self.initializing:
            logger.debug("Application is in initialization phase")
            return True
        if not self.alive:
            logger.warning("Application is not running")
            return False
        if not self.plex:
            logger.warning("Plex server is not initialized yet")
            return False
        if not self.plex.is_alive:
            logger.warning("Connection to Plex server is not active")
            return False
        return True

    def set_signal_handlers(self) -> None:
        """
        Set up handlers for SIGINT and SIGTERM signals to allow graceful shutdown.

        This method registers signal handlers for SIGINT (Ctrl+C) and SIGTERM (termination signal)
        to ensure that the application can shut down gracefully when these signals are received.
        The handlers will call the stop() method to initiate the shutdown process.

        Returns:
            None
        """
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

    def stop(self, *_) -> None:
        """
        Handle termination signals (SIGINT or SIGTERM) by flagging the application to stop gracefully.

        This method sets the appropriate flags to indicate that the application should
        terminate its operations in a controlled manner. It does not immediately stop
        the application but signals that the shutdown process should begin.

        Args:
            *_ (Any): Variable arguments passed by the signal handler (not used).

        Returns:
            None
        """
        logger.info("Received termination signal, stopping gracefully")
        self.must_stop = True
        self.stop_signal = True

    def start(self) -> None:
        """
        Start the main loop of the application.

        This method implements the core application lifecycle:
        1. Starts the scheduler if enabled
        2. Enters the main loop that continues until a stop signal is received
        3. For each iteration, initializes the Plex server connection
        4. Monitors the connection health and restarts if necessary
        5. Performs cleanup operations when stopping
        6. Shuts down components when the application terminates

        The method includes robust error handling and automatic reconnection logic
        to ensure continuous operation even in case of temporary failures.

        Returns:
            None

        Raises:
            Exception: If an unrecoverable error occurs during initialization.
        """
        if self.scheduler:
            self.scheduler.start()

        while not self.stop_signal:
            self.must_stop = False
            self.initializing = True # Set initializing flag
            logger.info("Starting initialization phase...")
            try:
                self.init()
                if self.plex is None:
                    logger.error("Failed to initialize Plex server")
                    break

                # Start listening for alerts from the Plex server.
                self.plex.start_alert_listener(self.alert_listener_error_callback)
                self.alive = True
                logger.info("Application initialization completed successfully")
            except Exception as e:
                logger.error(f"Critical error during initialization: {str(e)}")
                raise
            finally:
                self.initializing = False # Clear initializing flag

            count = 0 # Counter for periodic health checks
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
                logger.info("Attempting to reestablish connection to the Plex server...")

        if self.scheduler:
            self.scheduler.shutdown()
            self.scheduler.join()

        # Shut down the health-check server
        self.healthcheck_server.shutdown()

    def alert_listener_error_callback(self, error: Exception) -> None:
        """
        Handle errors that occur in the Plex server alert listener.

        This callback is invoked when the alert listener encounters an error. It processes
        different types of exceptions and takes appropriate actions:
        - For WebSocket connection issues, it logs warnings
        - For Unicode decode errors, it logs a debug message and continues
        - For other unexpected errors, it logs detailed error information

        In most cases, it sets the must_stop flag to trigger a reconnection attempt.

        Args:
            error (Exception): The exception that occurred in the alert listener.

        Returns:
            None
        """
        if isinstance(error, WebSocketConnectionClosedException):
            logger.warning("WebSocket connection to the Plex server has been closed unexpectedly")
        elif isinstance(error, WebSocketTimeoutException):
            logger.warning("WebSocket connection to the Plex server has timed out")
        elif isinstance(error, UnicodeDecodeError):
            logger.debug("Received a malformed WebSocket payload - ignoring it")
            return
        else:
            logger.error(f"Unexpected error in alert listener: {str(error)}", exc_info=True)
        self.must_stop = True

    def scheduler_callback(self) -> None:
        """
        Callback function for scheduled tasks.

        This method is called by the scheduler at the configured intervals to perform
        periodic maintenance tasks. It checks if the Plex server is available and
        initiates a deep analysis of the media library if the server is alive.

        The deep analysis helps ensure that all media metadata is up-to-date and
        properly indexed for optimal performance.

        Returns:
            None
        """
        if self.plex is None or not self.plex.is_alive:
            return
        logger.info("[Scheduler] Deep analysis started")
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
