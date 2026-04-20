import logging
import os
from logging.handlers import RotatingFileHandler

from plex_auto_languages.utils.shared import get_platform_app_directory, is_docker


class CustomFormatter(logging.Formatter):
    """
    Custom log formatter with color-coded output for different log levels.

    This formatter applies different ANSI color codes to log messages based on
    their severity level, making logs more readable in terminal output.

    Attributes:
        grey (str): ANSI color code for grey text.
        blue (str): ANSI color code for blue text.
        yellow (str): ANSI color code for yellow text.
        red (str): ANSI color code for red text.
        bold_red (str): ANSI color code for bold red text.
        reset (str): ANSI code to reset text formatting.
        fmt (str): The log message format string.
        FORMATS (dict): Mapping of log levels to their formatted strings with colors.
    """
    grey = "\x1b[38;21m"
    blue = "\x1b[38;5;39m"
    yellow = "\x1b[38;5;226m"
    red = "\x1b[38;5;196m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    fmt = "%(asctime)s [%(levelname)s] %(message)s"

    FORMATS = {
        logging.DEBUG: grey + fmt + reset,
        logging.INFO: blue + fmt + reset,
        logging.WARNING: yellow + fmt + reset,
        logging.ERROR: red + fmt + reset,
        logging.CRITICAL: bold_red + fmt + reset
    }

    def format(self, record):
        """
        Format the log record with appropriate color based on log level.

        Args:
            record (logging.LogRecord): The log record to format.

        Returns:
            str: The formatted log message with color coding.
        """
        log_fmt = self.FORMATS.get(record.levelno, self.grey + self.fmt + self.reset)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def _get_log_directory() -> str:
    """
    Determines the log directory based on platform and container environment.

    Returns:
        str: Absolute path to the log directory.
    """
    if is_docker():
        return "/logs"

    app_directory = get_platform_app_directory("PlexAutoLanguages")
    if app_directory is None:
        return os.path.join(os.getcwd(), "logs")
    return os.path.join(app_directory, "logs")


def init_logger() -> logging.Logger:
    """
    Initialize and configure the application logger.

    Creates a logger with both console and rotating file handlers. Ensures
    handlers are only added once and prevents propagation to avoid duplicates.

    Returns:
        logging.Logger: Configured logger instance ready for use.
    """
    logger = logging.getLogger("Logger")
    logger.setLevel(logging.INFO)

    has_console_handler = any(type(handler) is logging.StreamHandler for handler in logger.handlers)
    if not has_console_handler:
        logger_stream_handler = logging.StreamHandler()
        logger_stream_handler.setFormatter(CustomFormatter())
        logger.addHandler(logger_stream_handler)

    has_file_handler = any(type(handler) is RotatingFileHandler for handler in logger.handlers)
    if not has_file_handler:
        try:
            log_directory = _get_log_directory()
            os.makedirs(log_directory, exist_ok=True)
            log_file = os.path.join(log_directory, "plex_auto_languages.log")

            logger_file_handler = RotatingFileHandler(
                filename=log_file,
                maxBytes=10 * 1024 * 1024,
                backupCount=10,
                encoding="utf-8"
            )
            logger_file_handler.setFormatter(logging.Formatter(CustomFormatter.fmt))
            logger.addHandler(logger_file_handler)
        except OSError as exception:
            logger.warning(f"Could not initialize file logging: {exception}")

    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    """
    Retrieve the application logger instance.

    This function provides a convenient way to access the logger
    from anywhere in the application without reinitializing it.

    Returns:
        logging.Logger: The application's logger instance.
    """
    return logging.getLogger("Logger")
