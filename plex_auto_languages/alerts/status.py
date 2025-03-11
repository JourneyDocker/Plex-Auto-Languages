from __future__ import annotations
from typing import TYPE_CHECKING

from plex_auto_languages.alerts.base import PlexAlert
from plex_auto_languages.utils.logger import get_logger
from plex_auto_languages.constants import EventType

if TYPE_CHECKING:
    from plex_auto_languages.plex_server import PlexServer


logger = get_logger()


class PlexStatus(PlexAlert):
    """
    Handles status update events from Plex server.

    This class processes status notifications such as library scan completions
    and manages the processing of newly added or updated episodes in the library.
    It triggers appropriate track selection actions based on the event type.

    Attributes:
        TYPE (str): The alert type identifier ('status').
    """

    TYPE = "status"

    @property
    def title(self) -> str:
        """
        Gets the status event title from the message.

        Returns:
            str: The title of the status event (e.g., 'Library scan complete').
        """
        return self._message.get("title", None)

    def process(self, plex: 'PlexServer') -> None:
        """
        Processes the status event and triggers appropriate actions.

        This method handles library scan completion events by:
        1. Refreshing the library cache or fetching recently added episodes
        2. Processing newly added episodes for all users
        3. Processing updated episodes for all users
        4. Applying appropriate track selection based on user preferences

        Args:
            plex (PlexServer): The Plex server instance to interact with.

        Returns:
            None
        """
        if self.title != "Library scan complete":
            return
        logger.debug("[Status] The Plex server scanned the library")

        if plex.config.get("refresh_library_on_scan"):
            added, updated = plex.cache.refresh_library_cache()
        else:
            added = plex.get_recently_added_episodes(minutes=5)
            updated = []

        # Process recently added episodes
        if len(added) > 0:
            logger.debug(f"[Status] Found {len(added)} newly added episode(s)")
            for item in added:
                # Check if the item should be ignored
                if plex.should_ignore_show(item.show()):
                    continue

                # Check if the item has already been processed
                if not plex.cache.should_process_recently_added(item.key, item.addedAt):
                    continue

                # Change tracks for all users
                logger.info(f"[Status] Processing newly added episode {plex.get_episode_short_name(item)}")
                plex.process_new_or_updated_episode(item.key, EventType.NEW_EPISODE, True)

        # Process updated episodes
        if len(updated) > 0:
            logger.debug(f"[Status] Found {len(updated)} updated episode(s)")
            for item in updated:
                # Check if the item should be ignored
                if plex.should_ignore_show(item.show()):
                    continue

                # Check if the item has already been processed
                if not plex.cache.should_process_recently_updated(item.key):
                    continue

                # Change tracks for all users
                logger.info(f"[Status] Processing updated episode {plex.get_episode_short_name(item)}")
                plex.process_new_or_updated_episode(item.key, EventType.UPDATED_EPISODE, False)
