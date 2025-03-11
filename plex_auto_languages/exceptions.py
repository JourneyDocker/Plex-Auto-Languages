class InvalidConfiguration(Exception):
    """
    Exception raised when the application configuration is invalid or incomplete.

    This exception is raised when the configuration file or settings provided
    to the application contain errors, missing required values, or invalid
    data that would prevent proper operation of the system.

    Common scenarios:
        - Missing required configuration fields
        - Invalid data types for configuration values
        - Incompatible setting combinations
        - Malformed configuration file
        - Invalid paths or URLs
        - Invalid authentication credentials

    Attributes:
        message (str): Explanation of the configuration error. Inherited from Exception.
    """
    pass


class UserNotFound(Exception):
    """
    Exception raised when a requested Plex user cannot be found.

    This exception is raised when operations attempt to access or modify
    settings for a Plex user that does not exist or is not accessible
    with the current authentication credentials.

    Common scenarios:
        - User ID doesn't exist in the Plex system
        - User has been deleted or deactivated
        - Current authentication lacks permission to access the user
        - User hasn't accepted the Plex share invitation
        - User lookup with invalid or expired credentials

    Attributes:
        message (str): Description of the user lookup error. Inherited from Exception.
    """
    pass
