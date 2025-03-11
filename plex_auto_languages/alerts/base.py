from __future__ import annotations
from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from plex_auto_languages.plex_server import PlexServer


class PlexAlert:
    """
    Base class for all Plex alert types that process server events.

    This abstract class defines the common interface and functionality for
    different types of Plex alerts. Each subclass handles specific event
    types from the Plex server and implements custom processing logic.

    Attributes:
        TYPE (str): Class attribute identifying the alert type. Must be
            overridden by subclasses with a specific alert type identifier.
        _message (Dict[str, Any]): The raw event message data from Plex.
    """

    TYPE = None

    def __init__(self, message: Dict[str, Any]):
        """
        Initialize a new PlexAlert instance.

        Args:
            message (Dict[str, Any]): The raw event message data from Plex
                containing details about the event.
        """
        self._message = message

    @property
    def message(self) -> Dict[str, Any]:
        """
        Get the raw event message data.

        Returns:
            Dict[str, Any]: The complete message dictionary containing
                all event data from Plex.
        """
        return self._message

    def process(self, plex: 'PlexServer') -> None:
        """
        Process the alert event and perform appropriate actions.

        This is an abstract method that must be implemented by all subclasses
        to define how each alert type should be handled.

        Args:
            plex (PlexServer): The Plex server instance to interact with
                when processing the alert.

        Returns:
            None

        Raises:
            NotImplementedError: If the subclass does not implement this method.
        """
        raise NotImplementedError
