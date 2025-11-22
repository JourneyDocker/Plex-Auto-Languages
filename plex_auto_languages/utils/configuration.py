import os
import re
import sys
import pathlib
import logging
from collections.abc import Mapping
import yaml
import warnings

from plex_auto_languages.utils.logger import get_logger
from plex_auto_languages.exceptions import InvalidConfiguration


logger = get_logger()


sensitive_keys = {"PLEX_TOKEN", "PLEX_URL", "NOTIFICATIONS_APPRISE_CONFIGS"}


def to_env_key(path):
    return path.replace('.', '_').upper()


def mask_value(key, value):
    if to_env_key(key) in sensitive_keys:
        if isinstance(value, str):
            return value[:4] + '*' * max(0, len(value) - 4)
        else:
            return '***'
    return value


def is_env_set(path):
    env_key = to_env_key(path)
    return env_key in os.environ


def log_config_values(config_dict, prefix=""):
    for key, value in config_dict.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            log_config_values(value, full_key)
        else:
            if not is_env_set(full_key):
                masked = mask_value(full_key, value)
                logger.info(f"Setting from Config: {full_key}={masked}")


def deep_dict_update(original, update):
    """
    Recursively updates a dictionary with values from another dictionary.

    This function performs a deep merge of two dictionaries, preserving nested
    structures and only overwriting values at the leaf level.

    Args:
        original (dict): The original dictionary to be updated
        update (dict): The dictionary containing values to update with

    Returns:
        dict: The updated dictionary with merged values
    """
    for key, value in update.items():
        if isinstance(value, Mapping):
            original[key] = deep_dict_update(original.get(key, {}), value)
        else:
            original[key] = value
    return original


def env_dict_update(original, var_name: str = ""):
    """
    Updates dictionary values from environment variables.

    Recursively traverses a dictionary and replaces values with corresponding
    environment variables if they exist. Environment variable names are constructed
    by converting dictionary keys to uppercase and joining with underscores.

    Args:
        original (dict): The dictionary to update with environment variables
        var_name (str): The parent variable name prefix for nested dictionaries

    Returns:
        dict: The updated dictionary with values from environment variables
    """

    for key, value in original.items():
        new_var_name = (f"{var_name}_{key}" if var_name != "" else key).upper()
        if isinstance(value, Mapping):
            original[key] = env_dict_update(original[key], new_var_name)
        elif new_var_name in os.environ:
            if "schedule_time" in new_var_name.lower():
                original[key] = os.environ.get(new_var_name)
            else:
                original[key] = yaml.safe_load(os.environ.get(new_var_name))
            masked = mask_value(new_var_name, original[key])
            logger.info(f"Setting from Env: {new_var_name.lower()}={masked}")
    return original


def is_docker():
    """
    Determines if the application is running inside a Docker container.

    Checks multiple indicators to detect Docker environment:
    1. Presence of /.dockerenv file
    2. Docker references in /proc/self/cgroup
    3. CONTAINERIZED environment variable set to "true"

    Returns:
        bool: True if running in Docker, False otherwise
    """
    path = "/proc/self/cgroup"
    return (
        os.path.exists("/.dockerenv") or
        os.path.isfile(path) and any("docker" in line for line in open(path, "r", encoding="utf-8")) or
        os.getenv("CONTAINERIZED", "False").lower() == "true"
    )


class Configuration:
    """
    Manages application configuration from multiple sources.

    This class handles loading, merging, validating, and accessing configuration
    settings from default values, user config files, environment variables, and
    Docker secrets. It provides a unified interface for accessing configuration
    parameters throughout the application.

    Attributes:
        _config (dict): The complete configuration dictionary with all settings
    """

    def __init__(self, user_config_path: str):
        """
        Initializes the Configuration object.

        Loads configuration from default settings, user config file, environment
        variables, and Docker secrets. Validates the configuration and sets up
        system-specific settings.

        Args:
            user_config_path (str): Path to the user's configuration file

        Raises:
            InvalidConfiguration: If the configuration fails validation
        """
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        default_config_path = os.path.join(root_dir, "config", "default.yaml")
        with open(default_config_path, "r", encoding="utf-8") as stream:
            self._config = yaml.safe_load(stream).get("plexautolanguages", {})
        if user_config_path is not None and os.path.exists(user_config_path):
            logger.info(f"Parsing config file '{user_config_path}'")
            self._override_from_config_file(user_config_path)
        self._override_from_env()
        self._override_plex_secrets_from_files()
        self._postprocess_config()
        self._validate_config()
        self._add_system_config()
        if self.get("debug"):
            logger.setLevel(logging.DEBUG)
            logger.debug("Debug mode enabled")

    def get(self, parameter_path: str):
        """
        Retrieves a configuration value using a dot-notation path.

        Allows accessing nested configuration values using dot notation
        (e.g., "plex.token" to access self._config["plex"]["token"]).

        Args:
            parameter_path (str): Dot-notation path to the configuration parameter

        Returns:
            Any: The value of the requested configuration parameter

        Raises:
            KeyError: If the parameter path doesn't exist in the configuration
        """
        return self._get(self._config, parameter_path)

    def _get(self, config: dict, parameter_path: str):
        """
        Internal recursive method to retrieve nested configuration values.

        Args:
            config (dict): The configuration dictionary to search in
            parameter_path (str): Dot-notation path to the configuration parameter

        Returns:
            Any: The value of the requested configuration parameter

        Raises:
            KeyError: If the parameter path doesn't exist in the configuration
        """
        separator = "."
        if separator in parameter_path:
            splitted = parameter_path.split(separator)
            return self._get(config[splitted[0]], separator.join(splitted[1:]))
        return config[parameter_path]

    def _override_from_config_file(self, user_config_path: str):
        """
        Overrides default configuration with values from a user config file.

        Args:
            user_config_path (str): Path to the user's configuration file
        """
        with open(user_config_path, "r", encoding="utf-8") as stream:
            user_config = yaml.safe_load(stream).get("plexautolanguages", {})
        self._config = deep_dict_update(self._config, user_config)
        log_config_values(user_config)

    def _override_from_env(self):
        """
        Overrides configuration with values from environment variables.

        Uses env_dict_update to recursively update configuration values
        from corresponding environment variables.
        """
        self._config = env_dict_update(self._config)

    def _override_plex_secrets_from_files(self):
        """
        Overrides Plex token and URL with values from Docker secrets if available.

        Checks for Plex token and URL in Docker secrets locations or custom
        locations specified by PLEX_TOKEN_FILE and PLEX_URL_FILE environment variables.
        """
        # Handle Plex token secret
        plex_token_file_path = os.environ.get("PLEX_TOKEN_FILE", "/run/secrets/plex_token")
        if os.path.exists(plex_token_file_path):
            logger.info("Getting PLEX_TOKEN from Docker secret")
            with open(plex_token_file_path, "r", encoding="utf-8") as stream:
                plex_token = stream.readline().strip()
            self._config["plex"]["token"] = plex_token

        # Handle Plex URL secret
        plex_url_file_path = os.environ.get("PLEX_URL_FILE", "/run/secrets/plex_url")
        if os.path.exists(plex_url_file_path):
            logger.info("Getting PLEX_URL from Docker secret")
            with open(plex_url_file_path, "r", encoding="utf-8") as stream:
                plex_url = stream.readline().strip()
            self._config["plex"]["url"] = plex_url

    def _postprocess_config(self):
        """
        Performs post-processing on loaded configuration values.

        Converts comma-separated string values to lists for specific configuration
        parameters. Currently handles:
        - ignore_labels: Labels to be ignored during processing
        - ignore_libraries: Libraries to be ignored during processing

        These values may come from config files or environment variables as strings,
        and this method ensures they're properly converted to Python lists.
        """
        ignore_labels_config = self.get("ignore_labels")
        if isinstance(ignore_labels_config, str):
            self._config["ignore_labels"] = ignore_labels_config.split(",")

        ignore_libraries_config = self.get("ignore_libraries")
        if isinstance(ignore_libraries_config, str):
            self._config["ignore_libraries"] = ignore_libraries_config.split(",")

    def _validate_config(self):
        """
        Validates the configuration for required values and correct formats.

        Checks for required parameters, valid values for enumerated options,
        and proper formatting of specific parameters like schedule_time.

        Raises:
            InvalidConfiguration: If any validation check fails
        """
        if self.get("plex.url") == "":
            logger.error("A Plex URL is required")
            raise InvalidConfiguration
        if self.get("plex.token") == "":
            logger.error("A Plex Token is required")
            raise InvalidConfiguration
        if self.get("update_level") not in ["show", "season"]:
            logger.error("The 'update_level' parameter must be either 'show' or 'season'")
            raise InvalidConfiguration
        if self.get("update_strategy") not in ["all", "next"]:
            logger.error("The 'update_strategy' parameter must be either 'all' or 'next'")
            raise InvalidConfiguration
        if not isinstance(self.get("ignore_labels"), list):
            logger.error("The 'ignore_labels' parameter must be a list or a string-based comma separated list")
            raise InvalidConfiguration
        if not isinstance(self.get("ignore_libraries"), list):
            logger.error("The 'ignore_libraries' parameter must be a list or a string-based comma separated list")
            raise InvalidConfiguration
        if self.get("scheduler.enable") and not re.match(r"^\d{2}:\d{2}$", str(self.get("scheduler.schedule_time"))):
            logger.error("A valid 'schedule_time' parameter with the format 'HH:MM' is required (ex: \"02:30\")")
            raise InvalidConfiguration
        if self.get("data_path") != "" and not os.path.exists(self.get("data_path")):
            logger.error("The 'data_path' parameter must be a valid path")
            raise InvalidConfiguration
        logger.info("The provided configuration has been successfully validated")

    def _add_system_config(self):
        """
        Adds system-specific configuration values.

        Determines if running in Docker and sets up the data directory
        based on the platform and configuration.
        """
        self._config["docker"] = is_docker()
        self._config["data_dir"] = self._get_data_directory("PlexAutoLanguages")
        if not os.path.exists(self._config["data_dir"]):
            os.makedirs(self._config["data_dir"])

    def _get_data_directory(self, app_name: str):
        """
        Determines the appropriate data directory for the application.

        Selects the data directory based on:
        1. User-specified data_path if provided
        2. Docker container path if running in Docker
        3. Platform-specific default locations

        Args:
            app_name (str): The name of the application for directory naming

        Returns:
            str: The path to the data directory

        Warns:
            If running on an unsupported operating system
        """
        home = pathlib.Path.home()
        data_path = self.get("data_path")
        if data_path is not None and data_path != "" and os.path.exists(data_path) and os.path.isdir(data_path):
            return os.path.join(data_path, app_name)
        if is_docker():
            return "/config"
        if sys.platform == "win32":
            return str(home / f"AppData/Roaming/{app_name}")
        if sys.platform == "linux":
            return str(home / f".local/share/{app_name}")
        if sys.platform == "darwin":
            return str(home / f"Library/Application Support/{app_name}")
        if os.uname()[0] == "FreeBSD":
            return str(home / f".local/share/{app_name}")
        warnings.warn("Warning: Unsupported Operating System!")
        return None
