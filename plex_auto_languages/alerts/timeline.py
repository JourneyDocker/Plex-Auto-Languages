from __future__ import annotations
from typing import TYPE_CHECKING
from datetime import datetime, timedelta
from plexapi.video import Episode

from plex_auto_languages.alerts.base import PlexAlert
from plex_auto_languages.utils.logger import get_logger
from plex_auto_languages.constants import EventType

if TYPE_CHECKING:
    from plex_auto_languages.plex_server import PlexServer


logger = get_logger()


class PlexTimeline(PlexAlert):
    """
    Handles timeline-related events from Plex server.

    This class processes timeline notifications for library items, particularly
    focusing on newly added episodes. It detects when new episodes are added to
    the library and triggers appropriate track selection actions.

    Attributes:
        TYPE (str): The alert type identifier ('timeline').
    """

    TYPE = "timeline"

    @property
    def has_metadata_state(self) -> bool:
        """
        Checks if the timeline event contains metadata state information.

        Returns:
            bool: True if the message contains metadata state, False otherwise.
        """
        return "metadataState" in self._message

    @property
    def has_media_state(self) -> bool:
        """
        Checks if the timeline event contains media state information.

        Returns:
            bool: True if the message contains media state, False otherwise.
        """
        return "mediaState" in self._message

    @property
    def item_id(self) -> int:
        """
        Gets the item ID from the timeline event.

        Returns:
            int: The unique identifier for the media item in Plex.
        """
        return int(self._message.get("itemID", None))

    @property
    def identifier(self) -> str:
        """
        Gets the identifier from the timeline event.

        Returns:
            str: The identifier string (e.g., 'com.plexapp.plugins.library').
        """
        return self._message.get("identifier", None)

    @property
    def state(self) -> int:
        """
        Gets the state value from the timeline event.

        Returns:
            int: The state value indicating the current status of the item.
        """
        return self._message.get("state", None)

    @property
    def entry_type(self) -> int:
        """
        Gets the entry type from the timeline event.

        Returns:
            int: The type value indicating the kind of timeline entry.
        """
        return self._message.get("type", None)

    def process(self, plex: 'PlexServer') -> None:
        """
        Processes the timeline event and triggers appropriate actions.

        This method handles timeline events by:
        1. Filtering out irrelevant events (metadata/media state changes, non-library events)
        2. Verifying the media is a TV show episode
        3. Checking if the library or show should be ignored
        4. Checking if the episode was recently added
        5. Ensuring the episode hasn't already been processed
        6. Triggering track selection for all users based on their preferences

        Args:
            plex (PlexServer): The Plex server instance to interact with.

        Returns:
            None
        """
        if self.has_metadata_state or self.has_media_state:
            return
        if self.identifier != "com.plexapp.plugins.library" or self.state != 5 or self.entry_type == -1:
            return

        # Skip if not an Episode
        item = plex.fetch_item(self.item_id)
        if item is None or not isinstance(item, Episode):
            return

        # Skip if the library should be ignored
        if plex.should_ignore_library(item.librarySectionTitle):
            logger.debug(f"[Timeline] Ignoring episode {item} due to ignored library: '{item.librarySectionTitle}'")
            return

        # Skip if the show should be ignored
        if plex.should_ignore_show(item.show()):
            logger.debug(f"[Timeline] Ignoring episode {item} due to Plex show labels")
            return

        # Check if the item has been added recently
        if item.addedAt < datetime.now() - timedelta(minutes=5):
            return

        # Check if the item has already been processed
        if not plex.cache.should_process_recently_added(item.key, item.addedAt):
            return

        # Change tracks for all users
        logger.info(f"[Timeline] Processing newly added episode {plex.get_episode_short_name(item)}")
        plex.process_new_or_updated_episode(self.item_id, EventType.NEW_EPISODE, True)
