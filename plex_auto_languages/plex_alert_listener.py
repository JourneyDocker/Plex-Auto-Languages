from __future__ import annotations
from typing import Callable, Optional
from websocket import WebSocketApp
from plexapi.alert import AlertListener
from plexapi.server import PlexServer as BasePlexServer

from plex_auto_languages.utils.logger import get_logger


logger = get_logger()


class PlexAlertListener(AlertListener):
    """
    A listener for Plex server alerts that extends the plexapi AlertListener.

    This class establishes a WebSocket connection to the Plex server to receive
    real-time alerts about various events (playback, library updates, etc.) and
    processes them through callback functions.

    Attributes:
        _server (BasePlexServer): The Plex server instance to listen to.
        _callback (Callable): Function called when an alert is received.
        _callbackError (Callable): Function called when an error occurs.
        _ws (WebSocketApp): The WebSocket connection to the Plex server.
    """

    def __init__(self, server: BasePlexServer, callback: Optional[Callable] = None, callbackError: Optional[Callable] = None):
        """
        Initialize the Plex alert listener.

        Args:
            server (BasePlexServer): The Plex server instance to connect to.
            callback (Optional[Callable]): Function to call when an alert is received.
                The function should accept a dictionary containing the alert data.
            callbackError (Optional[Callable]): Function to call when an error occurs.
                The function should accept an exception object.
        """
        super().__init__(server, callback, callbackError)

    def run(self) -> None:
        """
        Start the WebSocket connection to the Plex server.

        Establishes a persistent WebSocket connection to the Plex server's
        alert endpoint and begins listening for events. This method blocks
        until the connection is closed.

        Returns:
            None
        """
        url = self._server.url(self.key, includeToken=True).replace("http", "ws")
        self._ws = WebSocketApp(url, on_message=self._onMessage, on_error=self._onError)
        self._ws.run_forever(skip_utf8_validation=True)
