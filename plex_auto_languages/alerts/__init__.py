"""
Plex alert system module for handling various Plex server events.

This package contains alert classes that process different types of Plex events.
Each alert type is specialized to handle specific event data and trigger appropriate
actions based on the event content.

Classes:
    PlexAlert: Base class for all Plex alerts with common functionality.
    PlexActivity: Handles activity-related events from Plex.
    PlexPlaying: Processes media playback events.
    PlexTimeline: Manages timeline-related events for library items.
    PlexStatus: Handles status update events like library scans.
"""

from .base import PlexAlert             # noqa: F401
from .activity import PlexActivity      # noqa: F401
from .playing import PlexPlaying        # noqa: F401
from .timeline import PlexTimeline      # noqa: F401
from .status import PlexStatus          # noqa: F401
