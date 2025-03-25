import time
import requests
import itertools
from typing import Union, Callable, List, Tuple, Optional
from datetime import datetime, timedelta
from requests import ConnectionError as RequestsConnectionError
from plexapi.media import MediaPart
from plexapi.library import ShowSection
from plexapi.video import Episode, Show
from plexapi.exceptions import NotFound, Unauthorized, BadRequest
from plexapi.server import PlexServer as BasePlexServer

from plex_auto_languages.utils.logger import get_logger
from plex_auto_languages.utils.configuration import Configuration
from plex_auto_languages.plex_alert_handler import PlexAlertHandler
from plex_auto_languages.plex_alert_listener import PlexAlertListener
from plex_auto_languages.track_changes import TrackChanges, NewOrUpdatedTrackChanges
from plex_auto_languages.utils.notifier import Notifier
from plex_auto_languages.plex_server_cache import PlexServerCache
from plex_auto_languages.constants import EventType
from plex_auto_languages.exceptions import UserNotFound


logger = get_logger()


class UnprivilegedPlexServer():
    """
    Base class for interacting with a Plex server with limited privileges.

    This class provides core functionality for connecting to and querying a Plex server
    without requiring administrative access. It handles basic operations like fetching
    items, checking connection status, and retrieving media information.

    Attributes:
        _session (requests.Session): HTTP session for making requests to the Plex server.
        _plex_url (str): URL of the Plex server.
        _plex (BasePlexServer): The underlying PlexAPI server instance.
        _last_connection_check (datetime): Timestamp of the last connection check.
        _connection_status (bool): Cached connection status.
        _cached_sections (List): Cached library sections.
        _sections_cache_time (datetime): When the sections cache was last refreshed.
    """

    def __init__(self, url: str, token: str, session: requests.Session = requests.Session()):
        """
        Initialize an unprivileged Plex server connection.

        Args:
            url (str): The URL of the Plex server.
            token (str): Authentication token for the Plex server.
            session (requests.Session, optional): HTTP session to use for requests. Defaults to a new session.
        """
        self._session = session
        self._plex_url = url
        self._plex = self._get_server(url, token, self._session)
        self._last_connection_check = datetime.fromtimestamp(0)
        self._connection_status = False
        self._cached_sections = None
        self._sections_cache_time = datetime.fromtimestamp(0)

    @property
    def connected(self) -> bool:
        """
        Check if the connection to the Plex server is active.

        Caches the connection status for 2 minutes to prevent excessive API calls.

        Returns:
            bool: True if connected successfully, False otherwise.
        """
        # Early return if no Plex instance is available
        if self._plex is None:
            logger.debug("No Plex instance available")
            return False

        # Use cached status if it's recent enough
        cache_age = datetime.now() - self._last_connection_check
        if cache_age < timedelta(minutes=2):
            logger.debug(f"Using cached connection status: {'Connected' if self._connection_status else 'Disconnected'} "
                         f"(cache age: {cache_age.total_seconds():.1f}s)")
            return self._connection_status

        # Refresh connection status
        logger.debug("Connection status cache expired, refreshing")
        self._refresh_sections_cache()
        self._last_connection_check = datetime.now()
        logger.debug(f"Connection status: {'Connected' if self._connection_status else 'Disconnected'}")
        return self._connection_status

    @property
    def unique_id(self) -> str:
        """
        Get the unique identifier of the Plex server.

        Returns:
            str: The machine identifier of the Plex server.
        """
        return self._plex.machineIdentifier

    @staticmethod
    def _get_server(url: str, token: str, session: requests.Session) -> Optional[BasePlexServer]:
        """
        Create a connection to a Plex server.

        Args:
            url (str): The URL of the Plex server.
            token (str): Authentication token for the Plex server.
            session (requests.Session): HTTP session to use for requests.

        Returns:
            Optional[BasePlexServer]: A PlexAPI server instance if successful, None otherwise.
        """
        try:
            return BasePlexServer(url, token, session=session)
        except (RequestsConnectionError, Unauthorized):
            return None

    def fetch_item(self, item_id: Union[str, int]) -> Optional[object]:
        """
        Fetch a media item from the Plex server by its ID.

        Args:
            item_id (Union[str, int]): The ID of the item to fetch.

        Returns:
            Optional[object]: The requested media item if found, None otherwise.
        """
        try:
            return self._plex.fetchItem(item_id)
        except NotFound:
            return None

    def episodes(self) -> List[Episode]:
        """
        Get all episodes from the Plex server.

        Returns:
            List[Episode]: A list of all episodes in the Plex library.
        """
        return self._plex.library.all(libtype="episode", container_size=1000)

    def get_recently_added_episodes(self, minutes: int) -> List[Episode]:
        """
        Get episodes that were recently added to the Plex server.

        Args:
            minutes (int): Number of minutes to look back for recently added episodes.

        Returns:
            List[Episode]: A list of episodes added within the specified time frame.
        """
        episodes = []
        for section in self.get_show_sections():
            recent = section.searchEpisodes(sort="addedAt:desc", filters={"addedAt>>": f"{minutes}m"})
            episodes.extend(recent)
        return episodes

    def get_show_sections(self) -> List[ShowSection]:
        """
        Get all TV show sections from the Plex library.

        Returns:
            List[ShowSection]: A list of all TV show library sections.
        """
        return [s for s in self._plex.library.sections() if isinstance(s, ShowSection)]

    def _refresh_sections_cache(self) -> bool:
        """
        Refresh the cached library sections.

        Returns:
            bool: True if refresh was successful, False otherwise.
        """
        try:
            self._cached_sections = self._plex.library.sections()
            self._sections_cache_time = datetime.now()
            self._connection_status = True
            return True
        except (BadRequest, RequestsConnectionError) as e:
            logger.debug(f"Failed to refresh sections cache: {type(e).__name__}: {str(e)}")
            self._connection_status = False
            return False
        except Exception as e:
            logger.warning(f"Unexpected error refreshing sections cache: {type(e).__name__}: {str(e)}")
            self._connection_status = False
            return False

    @staticmethod
    def get_last_watched_or_first_episode(show: Show) -> Optional[Episode]:
        """
        Get the most recently watched episode of a show, or the first episode if none have been watched.

        Args:
            show (Show): The show to get an episode from.

        Returns:
            Optional[Episode]: The last watched episode or first episode, None if the show has no episodes.
        """
        watched_episodes = show.watched()
        if len(watched_episodes) == 0:
            all_episodes = show.episodes()
            if len(all_episodes) == 0:
                return None
            return all_episodes[0]
        return watched_episodes[-1]

    @staticmethod
    def get_selected_streams(episode: Union[Episode, MediaPart]) -> Tuple[Optional[object], Optional[object]]:
        """
        Get the currently selected audio and subtitle streams for an episode.

        Args:
            episode (Union[Episode, MediaPart]): The episode or media part to check.

        Returns:
            Tuple[Optional[object], Optional[object]]: A tuple containing the selected audio stream and subtitle stream.
        """
        audio_stream = ([a for a in episode.audioStreams() if a.selected] + [None])[0]
        subtitle_stream = ([s for s in episode.subtitleStreams() if s.selected] + [None])[0]
        return audio_stream, subtitle_stream

    @staticmethod
    def get_episode_short_name(episode: Episode, include_show: bool = True) -> str:
        """
        Get a short, formatted name for an episode.

        Args:
            episode (Episode): The episode to get a name for.
            include_show (bool, optional): Whether to include the show title in the name. Defaults to True.

        Returns:
            str: A formatted string representing the episode, e.g., "'Show Title' (S01E02)" or "S01E02".
        """
        try:
            season_num = episode.seasonNumber if episode.seasonNumber is not None else 0
            episode_num = episode.episodeNumber if episode.episodeNumber is not None else 0
            if include_show:
                show = episode.show()
                if show is None:
                    return f"Unknown Show (S{season_num:02}E{episode_num:02})"
                return f"'{show.title}' (S{season_num:02}E{episode_num:02})"
            return f"S{season_num:02}E{episode_num:02}"
        except Exception as e:
            logger.warning(f"Error getting episode name: {str(e)}")
            return "Unknown Episode"


class PlexServer(UnprivilegedPlexServer):
    """
    Extended Plex server class with administrative capabilities.

    This class extends UnprivilegedPlexServer with additional functionality for managing
    user accounts, handling alerts, processing media changes, and applying language preferences.

    Attributes:
        notifier (Notifier): Notification service for sending alerts about changes.
        config (Configuration): Configuration settings for the application.
        _user (object): The currently logged-in Plex user.
        _alert_handler (PlexAlertHandler): Handler for processing Plex server alerts.
        _alert_listener (PlexAlertListener): Listener for Plex server events.
        cache (PlexServerCache): Cache for storing Plex server data to improve performance.
    """

    def __init__(self, url: str, token: str, notifier: Notifier, config: Configuration):
        """
        Initialize a Plex server with administrative capabilities.

        Args:
            url (str): The URL of the Plex server.
            token (str): Authentication token for the Plex server.
            notifier (Notifier): Notification service for sending alerts.
            config (Configuration): Configuration settings for the application.

        Raises:
            UserNotFound: If the user associated with the provided token cannot be found.
        """
        super().__init__(url, token)
        self.notifier = notifier
        self.config = config
        self._user = self._get_logged_user()
        if self._user is None:
            logger.error("Unable to find the user associated with the provided Plex Token")
            raise UserNotFound
        logger.info(f"Successfully connected as user '{self.username}' (id: {self.user_id})")
        self._alert_handler = None
        self._alert_listener = None
        self.cache = PlexServerCache(self)

    @property
    def user_id(self) -> Optional[str]:
        """
        Get the ID of the currently logged-in user.

        Returns:
            Optional[str]: The user ID if available, None otherwise.
        """
        return self._user.id if self._user is not None else None

    @property
    def username(self) -> Optional[str]:
        """
        Get the name of the currently logged-in user.

        Returns:
            Optional[str]: The username if available, None otherwise.
        """
        return self._user.name if self._user is not None else None

    @property
    def is_alive(self) -> bool:
        """
        Check if the server connection and alert listener are active.

        Returns:
            bool: True if the server is connected and the alert listener is running, False otherwise.
        """
        return self.connected and self._alert_listener is not None and self._alert_listener.is_alive()

    @staticmethod
    def _get_server(url: str, token: str, session: requests.Session, max_tries: int = 300, retry_delay: int = 5) -> Optional[BasePlexServer]:
        """
        Attempts to establish a connection to the Plex server, retrying on failure.

        Args:
            url (str): The URL of the Plex server.
            token (str): Authentication token for the Plex server.
            session (requests.Session): HTTP session to use for requests.
            max_tries (int, optional): Maximum number of connection attempts. Defaults to 300.
            retry_delay (int, optional): Delay in seconds between retry attempts. Defaults to 5.

        Returns:
            Optional[BasePlexServer]: A PlexAPI server instance if successful, None after exhausting all attempts.
        """
        for attempt in range(1, max_tries + 1):
            try:
                return BasePlexServer(url, token, session=session)
            except Unauthorized:
                logger.warning(f"Unauthorized: Check your credentials. Retrying... (Attempt {attempt}/{max_tries})")
            except (RequestsConnectionError, BadRequest):
                logger.warning(f"Connection error: Unable to connect to Plex server. Retrying... (Attempt {attempt}/{max_tries})")
            except Exception as exc:
                logger.error(f"Unexpected error during connection to Plex: {exc}", exc_info=True)
            time.sleep(retry_delay)

        logger.error(f"Failed to connect to Plex server after {max_tries} attempts")
        return None

    def _get_logged_user(self) -> Optional[object]:
        """
        Retrieves the currently logged-in Plex system account.

        Returns:
            Optional[object]: The user account object if found, None otherwise.
        """
        if self._plex is None:
            return None
        try:
            plex_username = self._plex.myPlexAccount().username
            for account in self._plex.systemAccounts():
                if account.name == plex_username:
                    return account
        except Exception as e:
            logger.error(f"Error getting logged user: {str(e)}")
            return None
        return None

    def save_cache(self) -> None:
        """
        Save the current state of the server cache to disk.
        """
        self.cache.save()

    def start_alert_listener(self, error_callback: Callable) -> None:
        """
        Start listening for Plex server alerts.

        Sets up and starts a listener for various Plex events based on configuration settings.

        Args:
            error_callback (Callable): Function to call when an error occurs in the listener.
        """
        trigger_on_play = self.config.get("trigger_on_play")
        trigger_on_scan = self.config.get("trigger_on_scan")
        trigger_on_activity = self.config.get("trigger_on_activity")
        self._alert_handler = PlexAlertHandler(self, trigger_on_play, trigger_on_scan, trigger_on_activity)
        self._alert_listener = PlexAlertListener(self._plex, self._alert_handler, error_callback)
        logger.info("Starting alert listener")
        self._alert_listener.start()

    def get_instance_users(self) -> List[object]:
        """
        Get all users who have access to this Plex server instance.

        Attempts to retrieve users from cache first, then falls back to querying the Plex API.

        Returns:
            List[object]: A list of user objects with access to this server.
        """
        users = self.cache.get_instance_users()
        if users is not None:
            return users
        users = []
        try:
            for user in self._plex.myPlexAccount().users():
                server_identifiers = [share.machineIdentifier for share in user.servers]
                if self.unique_id in server_identifiers:
                    user.name = user.title
                    users.append(user)
            self.cache.set_instance_users(users)
            return users
        except BadRequest:
            logger.warning("Unable to retrieve the users of the account, falling back to cache")
            return self.cache.get_instance_users(check_validity=False)

    def get_all_user_ids(self) -> List[str]:
        """
        Get IDs of all users with access to this Plex server.

        Returns:
            List[str]: A list of user IDs, including the current user and all shared users.
        """
        return [self.user_id] + [user.id for user in self.get_instance_users()]

    def get_plex_instance_of_user(self, user_id: Union[int, str]) -> Optional['UnprivilegedPlexServer']:
        """
        Get a Plex server instance authenticated as a specific user.

        Creates a new UnprivilegedPlexServer instance with the specified user's token.

        Args:
            user_id (Union[int, str]): The ID of the user to authenticate as.

        Returns:
            Optional[UnprivilegedPlexServer]: A Plex server instance for the specified user, or None if unavailable.
        """
        if str(self.user_id) == str(user_id):
            return self
        matching_users = [u for u in self.get_instance_users() if str(u.id) == str(user_id)]
        if len(matching_users) == 0:
            logger.error(f"Unable to find user with id '{user_id}'")
            return None
        user = matching_users[0]
        user_token = self.cache.get_instance_user_token(user.id)
        if user_token is None:
            user_token = user.get_token(self.unique_id)
            self.cache.set_instance_user_token(user.id, user_token)
        user_plex = UnprivilegedPlexServer(self._plex_url, user_token, session=self._session)
        if not user_plex.connected:
            logger.error(f"Connection to the Plex server failed for user '{matching_users[0].name}'")
            return None
        return user_plex

    def get_user_from_client_identifier(self, client_identifier: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Get user information based on a client identifier.

        Args:
            client_identifier (str): The unique identifier of the client device.

        Returns:
            Tuple[Optional[str], Optional[str]]: A tuple containing the user ID and username, or (None, None) if not found.
        """
        plex_sessions = self._plex.sessions()
        current_players = list(itertools.chain.from_iterable([s.players for s in plex_sessions]))
        matching_players = [p for p in current_players if p.machineIdentifier == client_identifier]
        if len(matching_players) == 0:
            return (None, None)
        player = matching_players[0]
        user = self.get_user_by_id(player.userID)
        if user is None:
            return (None, None)
        return (user.id, user.name)

    def get_user_by_id(self, user_id: Union[int, str]) -> Optional[object]:
        """
        Get a user object by their ID.

        Args:
            user_id (Union[int, str]): The ID of the user to find.

        Returns:
            Optional[object]: The user object if found, None otherwise.
        """
        matching_users = [u for u in [self._user] + self.get_instance_users() if str(u.id) == str(user_id)]
        if len(matching_users) == 0:
            return None
        return matching_users[0]

    def should_ignore_show(self, show: Show) -> bool:
        """
        Check if a show should be ignored based on its labels.

        Args:
            show (Show): The show to check.

        Returns:
            bool: True if the show should be ignored, False otherwise.
        """
        for label in show.labels:
            if label.tag and label.tag in self.config.get("ignore_labels"):
                return True
        return False

    def process_new_or_updated_episode(self, item_id: Union[int, str], event_type: EventType, new: bool) -> None:
        """
        Process a newly added or updated episode for all users.

        Applies language preferences for all users who have access to the episode.

        Args:
            item_id (Union[int, str]): The ID of the episode.
            event_type (EventType): The type of event that triggered this processing.
            new (bool): Whether the episode is newly added (True) or updated (False).
        """
        track_changes = NewOrUpdatedTrackChanges(event_type, new)
        for user_id in self.get_all_user_ids():
            # Switch to the user's Plex instance
            user_plex = self.get_plex_instance_of_user(user_id)
            if user_plex is None:
                continue

            # Get the most recently watched episode or the first one of the show
            user_item = user_plex.fetch_item(item_id)
            if user_item is None:
                continue
            reference = user_plex.get_last_watched_or_first_episode(user_item.show())
            if reference is None:
                continue

            # Change tracks
            reference.reload()
            user_item.reload()
            user = self.get_user_by_id(user_id)
            if user is None:
                return
            track_changes.change_track_for_user(user.name, reference, user_item)

        # Notify changes
        if track_changes.has_changes:
            self.notify_changes(track_changes)

    def change_tracks(self, username: str, episode: Episode, event_type: EventType) -> None:
        """
        Change audio and subtitle tracks for an episode based on user preferences.

        Args:
            username (str): The name of the user whose preferences to apply.
            episode (Episode): The episode to modify.
            event_type (EventType): The type of event that triggered this change.
        """
        track_changes = TrackChanges(username, episode, event_type)
        # Get episodes to update
        episodes = track_changes.get_episodes_to_update(self.config.get("update_level"), self.config.get("update_strategy"))

        # Get changes to perform
        track_changes.compute(episodes)

        # Perform changes
        track_changes.apply()

        # Notify changes
        if track_changes.has_changes:
            self.notify_changes(track_changes)

    def notify_changes(self, track_changes: Union[TrackChanges, NewOrUpdatedTrackChanges]) -> None:
        """
        Send notifications about track changes.

        Args:
            track_changes (Union[TrackChanges, NewOrUpdatedTrackChanges]): The track changes to notify about.
        """
        logger.info(f"Language update: {track_changes.inline_description}")
        if self.notifier is None:
            return
        title = f"PlexAutoLanguages - {track_changes.title}"
        if isinstance(track_changes, TrackChanges):
            self.notifier.notify_user(title, track_changes.description, track_changes.username, track_changes.event_type)
        else:
            self.notifier.notify(title, track_changes.description, track_changes.event_type)

    def start_deep_analysis(self) -> None:
        """
        Perform a deep analysis of the Plex library.

        Processes recently played media and scans for newly added or updated episodes
        to apply language preferences.
        """
        # History
        min_date = datetime.now() - timedelta(days=1)
        history = self._plex.history(mindate=min_date)
        for episode in [media for media in history if isinstance(media, Episode)]:
            user = self.get_user_by_id(episode.accountID)
            if user is None:
                continue
            episode = episode.source()
            if episode is not None:
                episode.reload()
                self.change_tracks(user.name, episode, EventType.SCHEDULER)

        # Scan library
        added, updated = self.cache.refresh_library_cache()
        for item in added:
            if self.should_ignore_show(item.show()):
                continue
            if not self.cache.should_process_recently_added(item.key, item.addedAt):
                continue
            logger.info(f"[Scheduler] Processing newly added episode {self.get_episode_short_name(item)}")
            self.process_new_or_updated_episode(item.key, EventType.SCHEDULER, True)
        for item in updated:
            if self.should_ignore_show(item.show()):
                continue
            if not self.cache.should_process_recently_updated(item.key):
                continue
            logger.info(f"[Scheduler] Processing updated episode {self.get_episode_short_name(item)}")
            self.process_new_or_updated_episode(item.key, EventType.SCHEDULER, False)

    def stop(self) -> None:
        """
        Stop the Plex server alert listener.

        Gracefully shuts down the alert handler if it's running.
        """
        if self._alert_handler:
            self._alert_handler.stop()
