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


class PlexActivity(PlexAlert):
    """
    Handles activity-related events from Plex server.

    This class processes activity notifications such as library refreshes,
    section updates, and media generation events. It specifically focuses
    on handling completed library refresh events to trigger automatic
    language track selection.

    Attributes:
        TYPE (str): The alert type identifier ('activity').
        TYPE_LIBRARY_REFRESH_ITEM (str): Constant for library refresh events.
        TYPE_LIBRARY_UPDATE_SECTION (str): Constant for library section update events.
        TYPE_PROVIDER_SUBSCRIPTIONS_PROCESS (str): Constant for provider subscription events.
        TYPE_MEDIA_GENERATE_BIF (str): Constant for media BIF generation events.
    """

    TYPE = "activity"

    TYPE_LIBRARY_REFRESH_ITEM = "library.refresh.items"
    TYPE_LIBRARY_UPDATE_SECTION = "library.update.section"
    TYPE_PROVIDER_SUBSCRIPTIONS_PROCESS = "provider.subscriptions.process"
    TYPE_MEDIA_GENERATE_BIF = "media.generate.bif"

    def is_type(self, activity_type: str) -> bool:
        """
        Checks if the current activity matches the specified type.

        Args:
            activity_type (str): The activity type to check against.

        Returns:
            bool: True if the activity type matches, False otherwise.
        """
        return self.type == activity_type

    @property
    def event(self) -> str:
        """
        Gets the event status from the message.

        Returns:
            str: The event status (e.g., 'ended', 'started').
        """
        return self._message.get("event", None)

    @property
    def type(self) -> str:
        """
        Gets the activity type from the message.

        Returns:
            str: The activity type (e.g., 'library.refresh.items').
        """
        return self._message.get("Activity", {}).get("type", None)

    @property
    def item_key(self) -> str:
        """
        Gets the item key from the activity context.

        Returns:
            str: The key identifying the media item in Plex.
        """
        return self._message.get("Activity", {}).get("Context", {}).get("key", None)

    @property
    def user_id(self) -> str:
        """
        Gets the user ID associated with the activity.

        Returns:
            str: The Plex user ID who triggered the activity.
        """
        return self._message.get("Activity", {}).get("userID", None)

    def process(self, plex: PlexServer) -> None:
        """
        Processes the activity event and triggers appropriate actions.

        This method handles library refresh events by checking if audio/subtitle
        tracks need to be changed for the refreshed item. It implements
        deduplication logic to prevent processing the same item multiple times
        in quick succession.

        Args:
            plex (PlexServer): The Plex server instance to interact with.

        Returns:
            None
        """
        if self.event != "ended":
            return
        if not self.is_type(self.TYPE_LIBRARY_REFRESH_ITEM):
            return

        # Switch to the user's Plex instance
        user_plex = plex.get_plex_instance_of_user(self.user_id)
        if user_plex is None:
            return

        # Skip if not an Episode
        item = user_plex.fetch_item(self.item_key)
        if item is None or not isinstance(item, Episode):
            return

        # Skip if the library or show should be ignored
        if plex.should_ignore_library(item.librarySectionTitle):
            logger.debug(f"[Activity] Ignoring show: '{item.show().title}' episode: 'S{item.seasonNumber:02}E{item.episodeNumber:02}' due to ignored library: '{item.librarySectionTitle}'")
            return

        # Skip if the show should be ignored
        if plex.should_ignore_show(item.show()):
            logger.debug(f"[Activity] Ignoring show: '{item.show().title}' episode: 'S{item.seasonNumber:02}E{item.episodeNumber:02}' due to Plex show labels")
            return

        # Skip if this item has already been seen in the last 3 seconds
        activity_key = (self.user_id, self.item_key)
        current_time = datetime.now()
        # Clean old entries from recent_activities
        plex.cache.recent_activities = {
            activity_key: timestamp for activity_key, timestamp in plex.cache.recent_activities.items()
            if timestamp > current_time - timedelta(seconds=10)
        }
        if activity_key in plex.cache.recent_activities and \
                plex.cache.recent_activities[activity_key] > current_time - timedelta(seconds=3):
            return
        plex.cache.recent_activities[activity_key] = current_time

        # Change tracks if needed
        item.reload()
        user = plex.get_user_by_id(self.user_id)
        if user is None:
            return
        logger.debug(f"[Activity] User: {user.name} | Show: '{item.show().title}' | Episode: 'S{item.seasonNumber:02}E{item.episodeNumber:02}'")
        plex.change_tracks(user.name, item, EventType.PLAY_OR_ACTIVITY)
