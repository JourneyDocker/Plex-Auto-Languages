from __future__ import annotations
from typing import TYPE_CHECKING
from plexapi.video import Episode

from plex_auto_languages.alerts.base import PlexAlert
from plex_auto_languages.utils.logger import get_logger
from plex_auto_languages.constants import EventType

if TYPE_CHECKING:
    from plex_auto_languages.plex_server import PlexServer


logger = get_logger()


class PlexPlaying(PlexAlert):
    """
    Handles media playback events from Plex server.

    This class processes notifications related to media playback sessions,
    tracking session states and managing audio/subtitle track selection
    for TV show episodes.

    Attributes:
        TYPE (str): The alert type identifier ('playing').
    """

    TYPE = "playing"

    @property
    def client_identifier(self) -> str:
        """
        Gets the client identifier from the message.

        Returns:
            str: The unique identifier of the client device playing the media.
        """
        return self._message.get("clientIdentifier", None)

    @property
    def item_key(self) -> str:
        """
        Gets the media item key from the message.

        Returns:
            str: The key identifying the media item in Plex.
        """
        return self._message.get("key", None)

    @property
    def session_key(self) -> str:
        """
        Gets the session key from the message.

        Returns:
            str: The unique identifier for the current playback session.
        """
        return self._message.get("sessionKey", None)

    @property
    def session_state(self) -> str:
        """
        Gets the current state of the playback session.

        Returns:
            str: The playback state (e.g., 'playing', 'paused', 'stopped').
        """
        return self._message.get("state", None)

    def process(self, plex: 'PlexServer') -> None:
        """
        Processes the playback event and manages track selection.

        This method handles media playback events by:
        1. Identifying the user and their Plex instance
        2. Verifying the media is a TV show episode
        3. Checking if the library or show should be ignored
        4. Tracking session state changes
        5. Managing session cache when playback stops
        6. Detecting changes in selected audio/subtitle streams
        7. Triggering track selection based on user preferences

        Args:
            plex (PlexServer): The Plex server instance to interact with.

        Returns:
            None
        """
        # Get User id and user's Plex instance
        if self.client_identifier not in plex.cache.user_clients:
            user_id, username = plex.get_user_from_client_identifier(self.client_identifier)
            if user_id is None:
                return
            plex.cache.user_clients[self.client_identifier] = (user_id, username)
        else:
            user_id, username = plex.cache.user_clients[self.client_identifier]
        user_plex = plex.get_plex_instance_of_user(user_id)
        if user_plex is None:
            return

        # Skip if not an Episode
        item = user_plex.fetch_item(self.item_key)
        if item is None or not isinstance(item, Episode):
            return

        # Skip if the library should be ignored
        if plex.should_ignore_library(item.librarySectionTitle):
            logger.debug(f"[Play Session] Ignoring episode {item} due to ignored library: '{item.librarySectionTitle}'")
            return

        # Skip if the show should be ignored
        if plex.should_ignore_show(item.show()):
            logger.debug(f"[Play Session] Ignoring episode {item} due to Plex show labels")
            return

        # Skip is the session state is unchanged
        if self.session_key in plex.cache.session_states and plex.cache.session_states[self.session_key] == self.session_state:
            return
        logger.debug(f"[Play Session] "
                     f"Session: {self.session_key} | State: '{self.session_state}' | User id: {user_id} | Episode: {item}")
        plex.cache.session_states[self.session_key] = self.session_state

        # Reset cache if the session is stopped
        if self.session_state == "stopped":
            logger.debug(f"[Play Session] End of session {self.session_key} for user {user_id}")
            del plex.cache.session_states[self.session_key]
            del plex.cache.user_clients[self.client_identifier]

        # Skip if selected streams are unchanged
        item.reload()
        audio_stream, subtitle_stream = plex.get_selected_streams(item)
        pair_id = (
            audio_stream.id if audio_stream is not None else None,
            subtitle_stream.id if subtitle_stream is not None else None
        )
        if item.key in plex.cache.default_streams and plex.cache.default_streams[item.key] == pair_id:
            return
        plex.cache.default_streams[item.key] = pair_id

        # Change tracks if needed
        plex.change_tracks(username, item, EventType.PLAY_OR_ACTIVITY)
