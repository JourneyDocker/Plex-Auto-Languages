from __future__ import annotations

import copy
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from dateutil.parser import isoparse

from plex_auto_languages.utils.logger import get_logger

if TYPE_CHECKING:
    from plex_auto_languages.plex_server import PlexServer

logger = get_logger()


class PlexServerCache:
    """
    Manages caching for Plex server data to improve performance and reduce API calls.

    This class handles persistent storage of various Plex server data including episode metadata,
    user information, playback states, and recently processed items. It provides methods to
    load, save, migrate, and refresh cached data.

    Attributes:
        _is_refreshing (bool): Flag indicating if a library refresh is in progress.
        _plex (PlexServer): Reference to the parent PlexServer instance.
        _lock (threading.RLock): Re-entrant lock guarding shared cache state.
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
        _legacy_cache_file_path (str): Legacy JSON cache path used for one-time migration.
        _db_path (str): Path to the SQLite cache database file.
        _cache_file_path (str): Backwards-compatible alias for cache storage path usage.
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
        self._plex = plex
        self._lock = threading.RLock()
        self._last_refresh = datetime.fromtimestamp(0)

        # Alerts cache (in-memory only)
        self.session_states = {}     # session_key: session_state
        self.default_streams = {}    # item_key: (audio_stream_id, substitle_stream_id)
        self.user_clients = {}       # client_identifier: user_id
        self.newly_added = {}        # episode_id: added_at
        self.newly_updated = {}      # episode_id: updated_at
        self.recent_activities = {}  # (user_id, item_id): timestamp

        # Users cache (in-memory only)
        self._instance_users = []
        self._instance_user_tokens = {}
        self._instance_users_valid_until = datetime.fromtimestamp(0)

        # Library cache (persisted in SQLite)
        self.episode_parts = {}

        self._legacy_cache_file_path, self._db_path = self._get_cache_paths()
        self._cache_file_path = self._db_path  # backwards-compatible internal attribute usage

        # Initialization: try loading persisted cache data.
        if not self._load():
            self.save()
            logger.info(
                "[Cache] Scanning all episodes from the Plex library. "
                "This action should only take a few seconds but can take several minutes for larger libraries"
            )
            self.refresh_library_cache()
            logger.info(f"[Cache] Scanned {len(self.episode_parts)} episodes from the library")

    @staticmethod
    def _datetime_to_str(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()

    @staticmethod
    def _parse_datetime(value: str | None, default: datetime | None = None) -> datetime | None:
        if not value:
            return default
        try:
            return isoparse(value)
        except Exception:
            return default

    def _get_cache_paths(self) -> tuple[str, str]:
        """
        Determines and prepares cache paths.

        Creates the cache directory if it doesn't exist.

        Returns:
            tuple[str, str]: (legacy_json_path, sqlite_db_path)

        Raises:
            Exception: If the cache directory cannot be created.
        """
        data_dir = self._plex.config.get("data_dir")
        cache_dir = os.path.join(data_dir, "cache")
        legacy_json_path = os.path.join(cache_dir, self._plex.unique_id)
        db_path = f"{legacy_json_path}.sqlite3"

        if not os.path.exists(cache_dir):
            try:
                os.makedirs(cache_dir)
                logger.debug(f"[Cache] Created cache directory at {cache_dir}")
            except Exception as e:
                logger.error(f"[Cache] Failed to create cache directory at {cache_dir}: {e}")
                raise

        return legacy_json_path, db_path

    def _connect(self) -> sqlite3.Connection:
        """
        Creates a SQLite connection configured for cache persistence.

        Returns:
            sqlite3.Connection: Configured SQLite connection.
        """
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _initialize_database(self) -> None:
        """
        Creates required SQLite tables if they do not already exist.

        Initializes the `episodes` table for per-episode cache data and the
        `system_metadata` table for cache-wide values.
        """
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    episode_key TEXT PRIMARY KEY,
                    newly_added_at TEXT NULL,
                    newly_updated_at TEXT NULL,
                    part_keys_json TEXT NOT NULL DEFAULT '[]'
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS system_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def _load(self) -> bool:
        """
        Loads cached data from persistent storage.

        Attempts to read cache data from SQLite first. If no SQLite database exists,
        tries a one-time migration from the legacy JSON cache file. If no usable cache
        is found, returns False to indicate a fresh cache should be created.

        Returns:
            bool: True if usable cache data was loaded, False otherwise.
        """
        logger.debug("[Cache] Attempting to load cache data")

        db_exists = os.path.exists(self._db_path) and os.path.isfile(self._db_path)
        legacy_exists = os.path.exists(self._legacy_cache_file_path) and os.path.isfile(self._legacy_cache_file_path)

        self._initialize_database()

        if db_exists:
            return self._load_from_database()

        if legacy_exists:
            return self._migrate_legacy_json_cache()

        logger.info("[Cache] Cache database not found. Creating a new cache before scanning the library")
        return False

    def _load_from_database(self) -> bool:
        """
        Loads cache data from the SQLite database.

        Reads episode rows and metadata, reconstructs in-memory structures, and validates
        that episode cache data is present. If the database appears corrupted, it is removed
        and False is returned so the cache can be rebuilt.

        Returns:
            bool: True if the SQLite cache was successfully loaded, False otherwise.
        """
        logger.debug(f"[Cache] Loading server cache from SQLite at {self._db_path}")

        try:
            with self._connect() as conn:
                episode_rows = conn.execute(
                    "SELECT episode_key, newly_added_at, newly_updated_at, part_keys_json FROM episodes"
                ).fetchall()
                last_refresh_row = conn.execute(
                    "SELECT value FROM system_metadata WHERE key = ?",
                    ("last_refresh",),
                ).fetchone()
        except sqlite3.DatabaseError as e:
            logger.warning(f"[Cache] SQLite cache appears corrupted, clearing database before retry: {e}")
            try:
                os.remove(self._db_path)
                logger.debug(f"[Cache] Removed corrupted cache database at {self._db_path}")
            except Exception as remove_error:
                logger.error(f"[Cache] Failed to remove corrupted cache database at {self._db_path}: {remove_error}")
            return False

        self.newly_added = {}
        self.newly_updated = {}
        self.episode_parts = {}

        for episode_key, newly_added_at, newly_updated_at, part_keys_json in episode_rows:
            try:
                part_keys = json.loads(part_keys_json) if part_keys_json else []
                if not isinstance(part_keys, list):
                    part_keys = []
            except json.JSONDecodeError:
                part_keys = []

            self.episode_parts[episode_key] = part_keys

            parsed_added_at = self._parse_datetime(newly_added_at)
            if parsed_added_at is not None:
                self.newly_added[episode_key] = parsed_added_at

            parsed_updated_at = self._parse_datetime(newly_updated_at)
            if parsed_updated_at is not None:
                self.newly_updated[episode_key] = parsed_updated_at

        self._last_refresh = datetime.fromtimestamp(0)
        if last_refresh_row and last_refresh_row[0]:
            self._last_refresh = self._parse_datetime(last_refresh_row[0], self._last_refresh) or datetime.fromtimestamp(0)

        # Check if episode_parts is empty; if so, we assume the initial scan was incomplete.
        if not self.episode_parts:
            logger.warning(
                "[Cache] The cache data is empty. This likely indicates that the initial library scan "
                "did not complete. Triggering a new scan"
            )
            return False

        logger.debug("[Cache] SQLite cache loaded successfully")
        return True

    def _migrate_legacy_json_cache(self) -> bool:
        """
        Migrates the legacy JSON cache file into the SQLite cache database.

        Parses legacy cache content, converts supported fields into in-memory structures,
        persists the converted data to SQLite, and renames the migrated JSON file.

        Returns:
            bool: True if migration produced usable cache data, False otherwise.
        """
        logger.info(f"[Cache] Found legacy JSON cache at {self._legacy_cache_file_path}, migrating to SQLite")

        try:
            with open(self._legacy_cache_file_path, "r", encoding="utf-8") as stream:
                cache = json.load(stream)
        except json.JSONDecodeError:
            logger.warning("[Cache] Legacy cache file is corrupted, skipping migration and starting fresh")
            try:
                os.remove(self._legacy_cache_file_path)
                logger.debug(f"[Cache] Removed corrupted legacy cache file at {self._legacy_cache_file_path}")
            except Exception as e:
                logger.error(f"[Cache] Failed to remove corrupted legacy cache file at {self._legacy_cache_file_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"[Cache] Failed to read legacy cache file at {self._legacy_cache_file_path}: {e}")
            return False

        self.newly_updated = {}
        raw_newly_updated = cache.get("newly_updated", {})
        if isinstance(raw_newly_updated, dict):
            for key, value in raw_newly_updated.items():
                parsed_value = self._parse_datetime(value)
                if parsed_value is not None:
                    self.newly_updated[key] = parsed_value

        self.newly_added = {}
        raw_newly_added = cache.get("newly_added", {})
        if isinstance(raw_newly_added, dict):
            for key, value in raw_newly_added.items():
                parsed_value = self._parse_datetime(value)
                if parsed_value is not None:
                    self.newly_added[key] = parsed_value

        raw_episode_parts = cache.get("episode_parts", {})
        self.episode_parts = {}
        if isinstance(raw_episode_parts, dict):
            for key, value in raw_episode_parts.items():
                self.episode_parts[key] = value if isinstance(value, list) else []

        self._last_refresh = self._parse_datetime(cache.get("last_refresh"), datetime.fromtimestamp(0)) or datetime.fromtimestamp(0)

        self.save()

        migrated_path = f"{self._legacy_cache_file_path}.json.migrated"
        try:
            os.replace(self._legacy_cache_file_path, migrated_path)
            logger.info(f"[Cache] Legacy cache migrated and renamed to {migrated_path}")
        except Exception as e:
            logger.warning(f"[Cache] Legacy cache migrated but rename failed: {e}")

        if not self.episode_parts:
            logger.warning(
                "[Cache] The migrated cache data is empty. This likely indicates that the initial "
                "library scan did not complete. Triggering a new scan"
            )
            return False

        return True

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
        with self._lock:
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
        with self._lock:
            if episode_id in self.newly_updated and self.newly_updated[episode_id] >= self._last_refresh:
                return False
            self.newly_updated[episode_id] = datetime.now()
            return True

    def did_episode_parts_change(self, episode) -> bool:
        """
        Check if an episode's media parts have changed since last check.

        Uses the existing episode_parts cache to detect file changes.
        This is used to determine if a metadataState event represents
        a real file upgrade (e.g., Sonarr) or just metadata refresh.

        Args:
            episode: The episode to check.

        Returns:
            bool: True if parts changed, False otherwise.
        """
        with self._lock:
            current_parts = []
            for part in episode.iterParts():
                if part.key:
                    current_parts.append(part.key)

            previous_parts = self.episode_parts.get(episode.key)
            self.episode_parts[episode.key] = current_parts
            self.save()

            if not previous_parts:
                return False

            return set(current_parts) != set(previous_parts)

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
        with self._lock:
            if self._is_refreshing:
                logger.debug("[Cache] The library cache is already being refreshed")
                return [], []

            self._is_refreshing = True
            try:
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
                return added, updated
            finally:
                self._is_refreshing = False

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

    def save(self) -> None:
        """
        Saves the current cache state to persistent storage.

        Serializes the in-memory cache state into SQLite by snapshot-writing episode rows
        and updating system metadata values.

        Raises:
            Exception: Logs an error if saving fails but doesn't re-raise the exception.
        """
        with self._lock:
            logger.debug(f"[Cache] Saving server cache to SQLite at {self._db_path}")
            try:
                with self._connect() as conn:
                    conn.execute("DELETE FROM episodes")

                    episode_keys = set(self.episode_parts.keys()) | set(self.newly_added.keys()) | set(self.newly_updated.keys())
                    for episode_key in episode_keys:
                        part_keys = self.episode_parts.get(episode_key, [])
                        if not isinstance(part_keys, list):
                            part_keys = []

                        conn.execute(
                            """
                            INSERT INTO episodes (episode_key, newly_added_at, newly_updated_at, part_keys_json)
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                episode_key,
                                self._datetime_to_str(self.newly_added.get(episode_key)),
                                self._datetime_to_str(self.newly_updated.get(episode_key)),
                                json.dumps(part_keys),
                            ),
                        )

                    last_refresh_value = self._datetime_to_str(self._last_refresh) or datetime.fromtimestamp(0).isoformat()
                    conn.execute(
                        """
                        INSERT INTO system_metadata (key, value)
                        VALUES (?, ?)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value
                        """,
                        ("last_refresh", last_refresh_value),
                    )
                    conn.commit()

                logger.debug("[Cache] Server cache successfully saved")
            except Exception as e:
                logger.error(f"[Cache] Failed to save server cache at {self._db_path}: {e}")

    def clean_idle_caches(self) -> None:
        """
        Clean old entries from in-memory caches to prevent memory leaks during idle periods.

        This method removes stale entries from caches that may accumulate over time
        even when the application is not actively processing events.
        """
        with self._lock:
            current_time = datetime.now()

            # Clean recent_activities (older than 10 seconds)
            self.recent_activities = {
                activity_key: timestamp for activity_key, timestamp in self.recent_activities.items()
                if timestamp > current_time - timedelta(seconds=10)
            }

            # Clean user_clients (older than 24 hours)
            self.user_clients = {
                client_identifier: client_info for client_identifier, client_info in self.user_clients.items()
                if isinstance(client_info, tuple)
                and len(client_info) >= 2
                and (len(client_info) < 3 or client_info[2] > current_time - timedelta(hours=24))
            }

            # Clean session_states (older than 24 hours)
            self.session_states = {
                session_key: session_info for session_key, session_info in self.session_states.items()
                if isinstance(session_info, tuple)
                and len(session_info) >= 1
                and (len(session_info) < 2 or session_info[1] > current_time - timedelta(hours=24))
            }

            # Clean default_streams if too large
            if len(self.default_streams) > 5000:
                import random

                # Remove 20% if over 5000, or 50% if over 10000
                if len(self.default_streams) > 10000:
                    num_to_remove = len(self.default_streams) // 2
                else:
                    num_to_remove = len(self.default_streams) // 5

                if num_to_remove > 0:
                    keys_to_remove = random.sample(list(self.default_streams.keys()), num_to_remove)
                    for key in keys_to_remove:
                        del self.default_streams[key]

            # Clean newly_added and newly_updated (older than last refresh)
            if self._last_refresh != datetime.fromtimestamp(0):
                self.newly_added = {
                    episode_id: added_at for episode_id, added_at in self.newly_added.items()
                    if added_at > self._last_refresh
                }
                self.newly_updated = {
                    episode_id: updated_at for episode_id, updated_at in self.newly_updated.items()
                    if updated_at > self._last_refresh
                }

            # Clean expired user caches
            if current_time > self._instance_users_valid_until:
                self._instance_users.clear()
                self._instance_user_tokens.clear()
                self._instance_users_valid_until = datetime.fromtimestamp(0)
