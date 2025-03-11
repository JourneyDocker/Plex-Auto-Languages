from typing import List, Union
from apprise import Apprise

from plex_auto_languages.constants import EventType


class Notifier:
    """
    Manages notification delivery to different targets based on configuration.

    This class handles both global notifications and user-specific notifications,
    with support for filtering by event types.

    Attributes:
        _global_apprise (ConditionalApprise): Handles global notifications to all users.
        _user_apprise (dict): Maps usernames to their ConditionalApprise instances.
    """

    def __init__(self, configs: List[Union[str, dict]]):
        """
        Initialize the Notifier with the provided configuration.

        Args:
            configs (List[Union[str, dict]]): List of notification configurations.
                Each config can be either a string URL or a dictionary with keys:
                - 'urls': Single URL string or list of URL strings
                - 'users': Optional username string or list of usernames
                - 'events': Optional event type string or list of event type strings
        """
        self._global_apprise = ConditionalApprise()
        self._user_apprise = {}

        for config in configs:
            if isinstance(config, str):
                self._add_urls([config])
            if isinstance(config, dict) and "urls" in config:
                urls = config.get("urls")
                urls = [urls] if isinstance(urls, str) else urls
                usernames = config.get("users", None)
                if usernames is None:
                    usernames = []
                elif isinstance(usernames, str):
                    usernames = [usernames]
                event_types = config.get("events", None)
                if event_types is None:
                    event_types = []
                elif isinstance(event_types, str):
                    event_types = [EventType[event_types.upper()]]
                elif isinstance(event_types, list):
                    event_types = [EventType[et.upper()] for et in event_types]
                self._add_urls(urls, usernames, event_types)

    def _add_urls(self, urls: List[str], usernames: List[str] = None, event_types: List[EventType] = None):
        """
        Add notification URLs to the appropriate Apprise instances.

        If usernames are provided, adds URLs to user-specific Apprise instances.
        Otherwise, adds URLs to the global Apprise instance.

        Args:
            urls (List[str]): List of notification service URLs to add.
            usernames (List[str], optional): List of usernames to add URLs for.
                If None or empty, URLs are added globally. Defaults to None.
            event_types (List[EventType], optional): List of event types to filter
                notifications for. Defaults to None.
        """
        if usernames is None or len(usernames) == 0:
            for url in urls:
                self._global_apprise.add(url)
            if event_types is not None:
                self._global_apprise.add_event_types(event_types)
            return
        for username in usernames:
            user_apprise = self._user_apprise.setdefault(username, ConditionalApprise())
            for url in urls:
                user_apprise.add(url)
            if event_types is not None:
                user_apprise.add_event_types(event_types)

    def notify(self, title: str, message: str, event_type: EventType) -> None:
        """
        Send a global notification to all configured services.

        The notification is only sent if the event type matches the configured
        event types for the global notifier.

        Args:
            title (str): The notification title.
            message (str): The notification message body.
            event_type (EventType): The type of event triggering this notification.
        """
        self._global_apprise.notify_if_needed(title, message, event_type)

    def notify_user(self, title: str, message: str, username: str, event_type: EventType) -> None:
        """
        Send a notification to a specific user and to global services.

        Sends the notification to both global services and user-specific services
        if the username exists in the configuration.

        Args:
            title (str): The notification title.
            message (str): The notification message body.
            username (str): The username to send the notification to.
            event_type (EventType): The type of event triggering this notification.
        """
        self._global_apprise.notify_if_needed(title, message, event_type)
        if username is None or username not in self._user_apprise:
            return
        user_apprise = self._user_apprise[username]
        user_apprise.notify_if_needed(title, message, event_type)


class ConditionalApprise(Apprise):
    """
    Extended Apprise class that supports conditional notifications based on event types.

    This class filters notifications based on configured event types, only sending
    notifications for matching event types or all events if no filters are set.

    Attributes:
        _event_types (set): Set of EventType values that this instance will notify for.
    """

    def __init__(self):
        """
        Initialize a new ConditionalApprise instance with an empty event type filter.
        """
        super().__init__()
        self._event_types = set()

    def add_event_type(self, event_type: EventType) -> None:
        """
        Add a single event type to the filter.

        Args:
            event_type (EventType): The event type to add to the filter.
        """
        self._event_types.add(event_type)

    def add_event_types(self, event_types: List[EventType]) -> None:
        """
        Add multiple event types to the filter.

        Args:
            event_types (List[EventType]): List of event types to add to the filter.
        """
        for event_type in event_types:
            self.add_event_type(event_type)

    def notify_if_needed(self, title: str, body: str, event_type: EventType) -> bool:
        """
        Send a notification if the event type matches the filter.

        If no event types are configured in the filter, all notifications are sent.
        Otherwise, only notifications with matching event types are sent.

        Args:
            title (str): The notification title.
            body (str): The notification message body.
            event_type (EventType): The type of event triggering this notification.

        Returns:
            bool: True if notification was sent, False otherwise.
        """
        if len(self._event_types) != 0 and event_type not in self._event_types:
            return False
        return self.notify(title=title, body=body)
