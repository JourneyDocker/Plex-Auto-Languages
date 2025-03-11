import logging


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


def init_logger() -> logging.Logger:
    """
    Initialize and configure the application logger.

    Creates a logger with a custom formatter that outputs color-coded logs
    to the console. Ensures handlers are only added once and prevents
    log propagation to avoid duplicate entries.

    Returns:
        logging.Logger: Configured logger instance ready for use.
    """
    logger = logging.getLogger("Logger")

    # Avoid adding handlers multiple times
    if not logger.hasHandlers():
        logger.setLevel(logging.INFO)
        logger_stream_handler = logging.StreamHandler()
        logger_stream_handler.setFormatter(CustomFormatter())
        logger.addHandler(logger_stream_handler)

    # Prevent propagation to root logger to avoid duplicate logs
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
