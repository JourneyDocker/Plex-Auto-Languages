from enum import Enum


class EventType(Enum):
    """
    Enumeration of event types used for notification filtering and categorization.

    This enum defines the different types of events that can occur in the application,
    allowing for consistent event identification and targeted notification delivery.

    Attributes:
        PLAY_OR_ACTIVITY (int): Represents a play or activity event (value: 0).
        NEW_EPISODE (int): Represents a new episode being added event (value: 1).
        UPDATED_EPISODE (int): Represents an episode update event (value: 2).
        SCHEDULER (int): Represents a scheduled task execution event (value: 3).
    """
    PLAY_OR_ACTIVITY = 0
    NEW_EPISODE = 1
    UPDATED_EPISODE = 2
    SCHEDULER = 3
