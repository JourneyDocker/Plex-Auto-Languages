from __future__ import annotations
import os
import json
import copy
from typing import TYPE_CHECKING
from datetime import datetime, timedelta
from dateutil.parser import isoparse

from plex_auto_languages.utils.logger import get_logger
from plex_auto_languages.utils.json_encoders import DateTimeEncoder

if TYPE_CHECKING:
    from plex_auto_languages.plex_server import PlexServer

logger = get_logger()

class PlexServerCache:
    """
    Manages caching for Plex server data to improve performance and reduce API calls.

    This class handles persistent storage of various Plex server data including episode metadata,
    user information, playback states, and recently processed items. It provides methods to
    load, save, and refresh cached data.

    Attributes:
        _is_refreshing (bool): Flag indicating if a library refresh is in progress.
        _encoder (DateTimeEncoder): JSON encoder that handles datetime objects.
        _plex (PlexServer): Reference to the parent PlexServer instance.
        _cache_file_path (str): Path to the cache file on disk.
        _last_refresh (datetime): Timestamp of the last library cache refresh.
        session_states (dict): Maps session keys to session states.
        default_streams (dict): Maps item keys to default audio and subtitle stream IDs.
        user_clients (dict): Maps client identifiers to user IDs.
        newly_added (dict): Maps episode IDs to their added timestamps.
        newly_updated (dict): Maps episode IDs to their updated timestamps.
        recent_activities (dict): Maps (user_id, item_id) tuples to activity timestamps.
        _instance_users (list): List of users with access to the Plex server.
        _instance_user_tokens (dict): Maps user IDs to their authentication tokens.
        _instance_users_valid_until (datetime): Expiration timestamp for cached user data.
        episode_parts (dict): Maps episode keys to their media part keys.
    """

    def __init__(self, plex: PlexServer):
        """
        Initialize the PlexServerCache with a reference to the PlexServer.

        Sets up the cache structure and attempts to load existing cache data from disk.
        If loading fails or no cache exists, initializes an empty cache and triggers
        a library scan.

        Args:
            plex (PlexServer): The PlexServer instance this cache belongs to.
        """
        self._is_refreshing = False
        self._encoder = DateTimeEncoder()
        self._plex = plex
        self._cache_file_path = self._get_cache_file_path()
        self._last_refresh = datetime.fromtimestamp(0)
        # Alerts cache
        self.session_states = {}     # session_key: session_state
        self.default_streams = {}    # item_key: (audio_stream_id, substitle_stream_id)
        self.user_clients = {}       # client_identifier: user_id
        self.newly_added = {}        # episode_id: added_at
        self.newly_updated = {}      # episode_id: updated_at
        self.recent_activities = {}  # (user_id, item_id): timestamp
        # Users cache
        self._instance_users = []
        self._instance_user_tokens = {}
        self._instance_users_valid_until = datetime.fromtimestamp(0)
        # Library cache
        self.episode_parts = {}

        # Initialization: Try loading the cache from file.
        if not self._load():
            # Create the cache file with the default empty state.
            self.save()
            logger.info("[Cache] Scanning all episodes from the Plex library. This action should only take a few seconds but can take several minutes for larger libraries")
            self.refresh_library_cache()
            logger.info(f"[Cache] Scanned {len(self.episode_parts)} episodes from the library")

    def should_process_recently_added(self, episode_id: str, added_at: datetime) -> bool:
        """
        Determines if a recently added episode should be processed.

        Checks if the episode has already been processed with the same timestamp.
        If not, records the episode as processed and returns True.

        Args:
            episode_id (str): The Plex key identifier for the episode.
            added_at (datetime): The timestamp when the episode was added.

        Returns:
            bool: True if the episode should be processed, False if it was already processed.
        """
        if episode_id in self.newly_added and self.newly_added[episode_id] == added_at:
            return False
        self.newly_added[episode_id] = added_at
        return True

    def should_process_recently_updated(self, episode_id: str) -> bool:
        """
        Determines if a recently updated episode should be processed.

        Checks if the episode has already been processed since the last library refresh.
        If not, records the episode as processed and returns True.

        Args:
            episode_id (str): The Plex key identifier for the episode.

        Returns:
            bool: True if the episode should be processed, False if it was already processed.
        """
        if episode_id in self.newly_updated and self.newly_updated[episode_id] >= self._last_refresh:
            return False
        self.newly_updated[episode_id] = datetime.now()
        return True

    def refresh_library_cache(self) -> tuple[list, list]:
        """
        Refreshes the cached library data by scanning all episodes in the Plex library.

        Updates the episode_parts dictionary with current data from the Plex server.
        Identifies episodes that have been added or updated since the last refresh.

        Returns:
            tuple[list, list]: A tuple containing two lists:
                - List of newly added episodes
                - List of updated episodes
        """
        if self._is_refreshing:
            logger.debug("[Cache] The library cache is already being refreshed")
            return [], []
        self._is_refreshing = True
        logger.debug("[Cache] Refreshing library cache")
        added = []
        updated = []
        new_episode_parts = {}
        for episode in self._plex.episodes():
            part_list = new_episode_parts.setdefault(episode.key, [])
            for part in episode.iterParts():
                part_list.append(part.key)
            if episode.key in self.episode_parts and set(self.episode_parts[episode.key]) != set(part_list):
                updated.append(episode)
            elif episode.key not in self.episode_parts:
                added.append(episode)
        self.episode_parts = new_episode_parts
        logger.debug("[Cache] Done refreshing library cache")
        self._last_refresh = datetime.now()
        self.save()
        self._is_refreshing = False
        return added, updated

    def get_instance_users(self, check_validity=True) -> list | None:
        """
        Retrieves the cached list of Plex server users.

        Args:
            check_validity (bool, optional): Whether to check if the cached data is still valid.
                Defaults to True.

        Returns:
            list | None: A copy of the cached users list, or None if the cache is invalid
                and check_validity is True.
        """
        if check_validity and datetime.now() > self._instance_users_valid_until:
            return None
        return copy.deepcopy(self._instance_users)

    def set_instance_users(self, instance_users: list) -> None:
        """
        Updates the cached list of Plex server users.

        Stores a deep copy of the users list and sets an expiration time.
        Also caches authentication tokens for each user.

        Args:
            instance_users (list): List of user objects to cache.
        """
        self._instance_users = copy.deepcopy(instance_users)
        self._instance_users_valid_until = datetime.now() + timedelta(hours=12)
        for user in self._instance_users:
            if str(user.id) in self._instance_user_tokens:
                continue
            self._instance_user_tokens[str(user.id)] = user.get_token(self._plex.unique_id)

    def get_instance_user_token(self, user_id: str) -> str | None:
        """
        Retrieves a cached authentication token for a specific user.

        Args:
            user_id (str): The ID of the user whose token to retrieve.

        Returns:
            str | None: The user's authentication token, or None if not found.
        """
        return self._instance_user_tokens.get(str(user_id), None)

    def set_instance_user_token(self, user_id: str, token: str) -> None:
        """
        Caches an authentication token for a specific user.

        Args:
            user_id (str): The ID of the user.
            token (str): The authentication token to cache.
        """
        self._instance_user_tokens[str(user_id)] = token

    def clear_instance_user_token(self, user_id: str) -> None:
        """
        Clears the cached authentication token for a specific user.

        Args:
            user_id (str): The ID of the user whose token to clear.
        """
        if str(user_id) in self._instance_user_tokens:
            del self._instance_user_tokens[str(user_id)]

    def _get_cache_file_path(self) -> str:
        """
        Determines the file path for the cache file.

        Creates the cache directory if it doesn't exist.

        Returns:
            str: The absolute path to the cache file.

        Raises:
            Exception: If the cache directory cannot be created.
        """
        data_dir = self._plex.config.get("data_dir")
        cache_dir = os.path.join(data_dir, "cache")
        cache_file = os.path.join(cache_dir, self._plex.unique_id)
        if not os.path.exists(cache_dir):
            try:
                os.makedirs(cache_dir)
                logger.debug(f"[Cache] Created cache directory at {cache_dir}")
            except Exception as e:
                logger.error(f"[Cache] Failed to create cache directory at {cache_dir}: {e}")
                raise
        return cache_file

    def _load(self) -> bool:
        """
        Loads cached data from the cache file.

        Attempts to read and parse the cache file. If the file doesn't exist or
        is corrupted, returns False to indicate a fresh cache should be created.

        Returns:
            bool: True if the cache was successfully loaded, False otherwise.
        """
        logger.debug("[Cache] Attempting to load cache file")
        if not os.path.exists(self._cache_file_path) or not os.path.isfile(self._cache_file_path):
            logger.info("[Cache] Cache file not found. Creating a new cache file before scanning the library")
            return False
        try:
            with open(self._cache_file_path, "r", encoding="utf-8") as stream:
                cache = json.load(stream)
            logger.debug("[Cache] Cache file loaded successfully")
        except json.JSONDecodeError:
            logger.warning("[Cache] The cache file is corrupted, clearing the cache before trying again")
            try:
                os.remove(self._cache_file_path)
                logger.debug(f"[Cache] Removed corrupted cache file at {self._cache_file_path}")
            except Exception as e:
                logger.error(f"[Cache] Failed to remove corrupted cache file at {self._cache_file_path}: {e}")
            return False

        self.newly_updated = cache.get("newly_updated", self.newly_updated)
        self.newly_updated = {key: isoparse(value) for key, value in self.newly_updated.items()}
        self.newly_added = cache.get("newly_added", self.newly_added)
        self.newly_added = {key: isoparse(value) for key, value in self.newly_added.items()}
        self.episode_parts = cache.get("episode_parts", )

        # Check if episode_parts is empty; if so, we assume the initial scan was incomplete.
        if not self.episode_parts:
            logger.warning(
                "[Cache] The cache data is empty. This likely indicates that the initial library scan did not complete. Triggering a new scan"
            )
            return False

        self._last_refresh = isoparse(cache.get("last_refresh", self._last_refresh))
        return True

    def save(self) -> None:
        """
        Saves the current cache state to the cache file.

        Serializes the cache data to JSON and writes it to the cache file.
        Uses a custom JSON encoder to handle datetime objects.

        Raises:
            Exception: Logs an error if saving fails but doesn't re-raise the exception.
        """
        logger.debug(f"[Cache] Saving server cache to file at {self._cache_file_path}")
        cache = {
            "newly_updated": self.newly_updated,
            "newly_added": self.newly_added,
            "episode_parts": self.episode_parts,
            "last_refresh": self._last_refresh
        }
        try:
            with open(self._cache_file_path, "w", encoding="utf-8") as stream:
                stream.write(self._encoder.encode(cache))
            logger.debug("[Cache] Server cache successfully saved")
        except Exception as e:
            logger.error(f"[Cache] Failed to save server cache at {self._cache_file_path}: {e}")

    def clean_idle_caches(self) -> None:
        """
        Clean old entries from in-memory caches to prevent memory leaks during idle periods.

        This method removes stale entries from caches that may accumulate over time
        even when the application is not actively processing events.
        """
        current_time = datetime.now()

        # Clean recent_activities (older than 10 seconds)
        self.recent_activities = {
            activity_key: timestamp for activity_key, timestamp in self.recent_activities.items()
            if timestamp > current_time - timedelta(seconds=10)
        }

        # Clean user_clients (older than 24 hours)
        self.user_clients = {
            client_identifier: client_info for client_identifier, client_info in self.user_clients.items()
            if isinstance(client_info, tuple) and len(client_info) >= 2 and (len(client_info) < 3 or client_info[2] > current_time - timedelta(hours=24))
        }

        # Clean session_states (older than 24 hours)
        self.session_states = {
            session_key: session_info for session_key, session_info in self.session_states.items()
            if isinstance(session_info, tuple) and len(session_info) >= 1 and (len(session_info) < 2 or session_info[1] > current_time - timedelta(hours=24))
        }

        # Clean default_streams if too large
        if len(self.default_streams) > 10000:
            import random
            num_to_remove = len(self.default_streams) // 10
            if num_to_remove > 0:
                keys_to_remove = random.sample(list(self.default_streams.keys()), num_to_remove)
                for key in keys_to_remove:
                    del self.default_streams[key]
