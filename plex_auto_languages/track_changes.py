from typing import List, Union, Optional, Tuple
from plexapi.video import Episode
from plexapi.media import AudioStream, SubtitleStream, MediaPart

from plex_auto_languages.utils.logger import get_logger
from plex_auto_languages.constants import EventType


logger = get_logger()


class TrackChanges():
    """
    Manages audio and subtitle track changes for Plex episodes.

    This class handles the detection, computation, and application of language track changes
    across episodes based on a reference episode's selected audio and subtitle tracks.

    Attributes:
        _reference (Episode): The reference episode used as a template for track changes.
        _username (str): The username associated with these track changes.
        _event_type (EventType): The type of event that triggered these changes.
        _audio_stream (AudioStream): The selected audio stream from the reference episode.
        _subtitle_stream (SubtitleStream): The selected subtitle stream from the reference episode.
        _changes (List[Tuple]): List of changes to be applied, each containing episode, part, stream type, and new stream.
        _description (str): Human-readable description of the changes.
        _title (str): Title for the change notification.
        _computed (bool): Whether changes have been computed.
    """

    def __init__(self, username: str, reference: Episode, event_type: EventType):
        """
        Initialize a TrackChanges instance.

        Args:
            username (str): The username associated with these track changes.
            reference (Episode): The reference episode used as a template.
            event_type (EventType): The type of event that triggered these changes.
        """
        self._reference = reference
        self._username = username
        self._event_type = event_type
        self._audio_stream, self._subtitle_stream = self._get_selected_streams(reference)
        self._changes = []
        self._description = ""
        self._title = ""
        self._computed = False

    @property
    def computed(self) -> bool:
        """
        Check if changes have been computed.

        Returns:
            bool: True if changes have been computed, False otherwise.
        """
        return self._computed

    @property
    def event_type(self) -> EventType:
        """
        Get the event type that triggered these changes.

        Returns:
            EventType: The event type.
        """
        return self._event_type

    @property
    def description(self) -> str:
        """
        Get a human-readable description of the changes.

        Returns:
            str: The description of changes.
        """
        return self._description

    @property
    def inline_description(self) -> str:
        """
        Get a single-line description of the changes.

        Returns:
            str: The description with newlines replaced by pipe separators.
        """
        return self._description.replace("\n", " | ")

    @property
    def title(self) -> str:
        """
        Get the title for the change notification.

        Returns:
            str: The title.
        """
        return self._title

    @property
    def reference_name(self) -> str:
        """
        Get a formatted name of the reference episode.

        Returns:
            str: The episode name in the format "Show Title (S01E02)".
        """
        return f"{self._reference.show().title} (S{self._reference.seasonNumber:02}E{self._reference.episodeNumber:02})"

    @property
    def has_changes(self) -> bool:
        """
        Check if there are any changes to apply.

        Returns:
            bool: True if there are changes, False otherwise.
        """
        return len(self._changes) > 0

    @property
    def username(self) -> str:
        """
        Get the username associated with these changes.

        Returns:
            str: The username.
        """
        return self._username

    @property
    def change_count(self) -> int:
        """
        Get the number of changes to apply.

        Returns:
            int: The number of changes.
        """
        return len(self._changes)

    def get_episodes_to_update(self, update_level: str, update_strategy: str) -> List[Episode]:
        """
        Get a list of episodes to update based on the update level and strategy.

        Args:
            update_level (str): The level at which to apply updates ('show' or 'season').
            update_strategy (str): The strategy for selecting episodes ('all' or 'next').

        Returns:
            List[Episode]: The list of episodes to update.
        """
        show_or_season = None
        if update_level == "show":
            show_or_season = self._reference.show()
        elif update_level == "season":
            show_or_season = self._reference.season()
        episodes = show_or_season.episodes()
        if update_strategy == "next":
            episodes = [e for e in episodes if self._is_episode_after(e)]
        return episodes

    def compute(self, episodes: List[Episode]) -> None:
        """
        Compute the track changes needed for the given episodes.

        Analyzes each episode to determine if audio or subtitle track changes are needed
        based on the reference episode's selected tracks.

        Args:
            episodes (List[Episode]): The list of episodes to analyze.
        """
        logger.debug(f"[Language Update] Checking language update for show "
                     f"{self._reference.show()} and user '{self._username}' based on episode {self._reference}")
        self._changes = []
        for episode in episodes:
            episode.reload()
            for part in episode.iterParts():
                current_audio_stream, current_subtitle_stream = self._get_selected_streams(part)
                # Audio stream
                matching_audio_stream = self._match_audio_stream(part.audioStreams())
                if current_audio_stream is not None and matching_audio_stream is not None and \
                        matching_audio_stream.id != current_audio_stream.id:
                    self._changes.append((episode, part, AudioStream.STREAMTYPE, matching_audio_stream))
                # Subtitle stream
                matching_subtitle_stream = self._match_subtitle_stream(part.subtitleStreams())
                if current_subtitle_stream is not None and matching_subtitle_stream is None:
                    self._changes.append((episode, part, SubtitleStream.STREAMTYPE, None))
                if matching_subtitle_stream is not None and \
                        (current_subtitle_stream is None or matching_subtitle_stream.id != current_subtitle_stream.id):
                    if current_audio_stream.title is not None and "commentary" in current_audio_stream.title.lower() and matching_audio_stream is None:
                        # if the changed stream was commentary but this ep has none, then don't touch subs
                        logger.debug(f"[Language Update] Skipping subtitle changes for "
                         f"episode {self._reference} and user '{self.username}'")
                    else:
                        self._changes.append((episode, part, SubtitleStream.STREAMTYPE, matching_subtitle_stream))
        self._update_description(episodes)
        self._computed = True

    def apply(self) -> None:
        """
        Apply the computed track changes to the episodes.

        Sets the selected audio and subtitle streams for each episode part
        according to the computed changes.
        """
        if not self.has_changes:
            logger.debug(f"[Language Update] No changes to perform for show "
                         f"{self._reference.show()} and user '{self.username}'")
            return
        logger.debug(f"[Language Update] Performing {len(self._changes)} change(s) for show {self._reference.show()}")
        for episode, part, stream_type, new_stream in self._changes:
            stream_type_name = "audio" if stream_type == AudioStream.STREAMTYPE else "subtitle"
            logger.debug(f"[Language Update] Updating {stream_type_name} stream of episode {episode} to {new_stream}")
            if stream_type == AudioStream.STREAMTYPE:
                part.setSelectedAudioStream(new_stream)
            elif stream_type == SubtitleStream.STREAMTYPE and new_stream is None:
                part.resetSelectedSubtitleStream()
            elif stream_type == SubtitleStream.STREAMTYPE:
                part.setSelectedSubtitleStream(new_stream)

    def _is_episode_after(self, episode: Episode) -> bool:
        """
        Check if an episode comes after the reference episode.

        Args:
            episode (Episode): The episode to check.

        Returns:
            bool: True if the episode comes after the reference, False otherwise.
        """
        return self._reference.seasonNumber < episode.seasonNumber or \
            (self._reference.seasonNumber == episode.seasonNumber and self._reference.episodeNumber < episode.episodeNumber)

    def _update_description(self, episodes: List[Episode]) -> None:
        """
        Update the description of the changes based on the affected episodes.

        Args:
            episodes (List[Episode]): The list of episodes affected by the changes.
        """
        if len(episodes) == 0:
            self._title = ""
            self._description = ""
            return

        valid_episodes = [e for e in episodes if e.seasonNumber is not None and e.episodeNumber is not None]
        invalid_episodes = [e for e in episodes if e.seasonNumber is None or e.episodeNumber is None]

        if valid_episodes:
            season_numbers = [e.seasonNumber for e in valid_episodes]
            min_season_number, max_season_number = min(season_numbers), max(season_numbers)
            min_episode_number = min([e.episodeNumber for e in valid_episodes if e.seasonNumber == min_season_number])
            max_episode_number = max([e.episodeNumber for e in valid_episodes if e.seasonNumber == max_season_number])
            from_str = f"S{min_season_number:02}E{min_episode_number:02}"
            to_str = f"S{max_season_number:02}E{max_episode_number:02}"
            range_str = f"{from_str} - {to_str}" if from_str != to_str else from_str
        else:
            range_str = f"Unable to determine range due to missing season or episode number for {len(invalid_episodes)} episode(s)"

        nb_updated = len({e.key for e, _, _, _ in self._changes})
        nb_total = len(episodes)
        self._title = self._reference.show().title
        self._description = (
            f"Show: {self._reference.show().title}\n"
            f"User: {self._username}\n"
            f"Audio: {self._audio_stream.displayTitle if self._audio_stream is not None else 'None'}\n"
            f"Subtitles: {self._subtitle_stream.displayTitle if self._subtitle_stream is not None else 'None'}\n"
            f"Updated episodes: {nb_updated}/{nb_total} ({range_str})"
        )

    def _match_audio_stream(self, audio_streams: List[AudioStream]) -> Optional[AudioStream]:
        """
        Find the best matching audio stream from a list of available streams.

        Matches based on language code, descriptive terms, visual impaired flag, codec,
        channel layout, and title similarity to the reference audio stream.

        Args:
            audio_streams (List[AudioStream]): The list of available audio streams.

        Returns:
            Optional[AudioStream]: The best matching audio stream, or None if no match found.
        """
        # The reference stream can be 'None'
        if self._audio_stream is None:
            return None

        # We only want streams with the same language code
        streams = [s for s in audio_streams if s.languageCode == self._audio_stream.languageCode]
        # Check if streams aren't differentiated
        ambiguous = all(s.title == audio_streams[0].title for s in audio_streams)

        def get_stream_title(stream):
            """Helper function to get the most specific title available"""
            return (stream.extendedDisplayTitle or
                    stream.displayTitle or
                    stream.title or "").lower()

        def contains_descriptive_terms(title):
            """Check if the title contains terms indicating a descriptive track"""
            descriptive_terms = [
                "commentary", "description", "descriptive",
                "narration", "narrative", "described"
            ]
            return any(term in title for term in descriptive_terms)

        # Get reference stream title
        ref_title = get_stream_title(self._audio_stream)

        # First, try to match visualImpaired flag if available
        try:
            # Check if the reference is a visual impaired track
            if hasattr(self._audio_stream, 'visualImpaired') and self._audio_stream.visualImpaired:
                # Keep only visual impaired tracks
                visual_impaired_streams = [s for s in streams if hasattr(s, 'visualImpaired') and s.visualImpaired]
                if visual_impaired_streams:
                    streams = visual_impaired_streams
            else:
                # Filter out visual impaired tracks if reference is not visual impaired
                non_visual_impaired_streams = [s for s in streams if not (hasattr(s, 'visualImpaired') and s.visualImpaired)]
                if non_visual_impaired_streams:
                    streams = non_visual_impaired_streams
        except (AttributeError, TypeError):
            # Fall back to descriptive terms if visualImpaired attribute is not available
            #logger.debug("visualImpaired attribute not available, falling back to title-based detection")
            pass

        # Fallback to descriptive terms in title
        if contains_descriptive_terms(ref_title):
            # Keep only descriptive tracks if reference is descriptive
            descriptive_streams = [s for s in streams if contains_descriptive_terms(get_stream_title(s))]
            if descriptive_streams:
                streams = descriptive_streams
        else:
            # Filter out descriptive tracks if reference is not descriptive
            non_descriptive_streams = [s for s in streams if not contains_descriptive_terms(get_stream_title(s))]
            if non_descriptive_streams:
                streams = non_descriptive_streams

        if len(streams) == 0:
            return None

        if len(streams) == 1:
            return streams[0]

        # If multiple streams match, order them based on a score
        scores = [0] * len(streams)
        for index, stream in enumerate(streams):
            # Codec match
            if self._audio_stream.codec == stream.codec:
                scores[index] += 5
            # Channel layout match
            if self._audio_stream.audioChannelLayout == stream.audioChannelLayout:
                scores[index] += 3
            # Handle ambiguous streams
            if ambiguous:
                if self._audio_stream.channels < 3:
                    if self._audio_stream.channels < stream.channels:
                        # Prefer more channels as a safe choice to avoid descriptive tracks (likely 2.0)
                        scores[index] += 8
                else:
                    if self._audio_stream.channels <= stream.channels:
                        scores[index] += 1

            # Individual title field matching
            #if self._audio_stream.extendedDisplayTitle is not None and stream.extendedDisplayTitle is not None and \
            #        self._audio_stream.extendedDisplayTitle == stream.extendedDisplayTitle:
            #    scores[index] += 5
            #if self._audio_stream.displayTitle is not None and stream.displayTitle is not None and \
            #        self._audio_stream.displayTitle == stream.displayTitle:
            #    scores[index] += 5
            if self._audio_stream.title is not None and stream.title is not None and \
                    self._audio_stream.title == stream.title:
                scores[index] += 5

        # Logging for debugging
        logger.debug(f"Audio scores: {scores}, Streams: {streams}")
        return streams[scores.index(max(scores))]

    def _match_subtitle_stream(self, subtitle_streams: List[SubtitleStream]) -> Optional[SubtitleStream]:
        """
        Find the best matching subtitle stream from a list of available streams.

        Matches based on language code, forced flag, hearing impaired flag,
        codec, and title similarity to the reference subtitle stream.

        Args:
            subtitle_streams (List[SubtitleStream]): The list of available subtitle streams.

        Returns:
            Optional[SubtitleStream]: The best matching subtitle stream, or None if no match found.
        """
        # If no subtitle is selected, the reference stream can be 'None'
        if self._subtitle_stream is None:
            if self._audio_stream is None:
                return None
            match_forced_only = True
            match_hearing_impaired_only = False
            language_code = self._audio_stream.languageCode
        else:
            match_forced_only = self._subtitle_stream.forced
            match_hearing_impaired_only = self._subtitle_stream.hearingImpaired
            language_code = self._subtitle_stream.languageCode

        # We only want streams with the same language code
        streams = [s for s in subtitle_streams if s.languageCode == language_code]
        if match_forced_only:
            streams = [s for s in streams if s.forced]
        if match_hearing_impaired_only:
            streams = [s for s in streams if s.hearingImpaired]

        if len(streams) == 0:
            return None

        if len(streams) == 1:
            return streams[0]

        # Score the remaining streams based on attributes
        scores = [0] * len(streams)
        for index, stream in enumerate(streams):
            if self._subtitle_stream is not None:
                if self._subtitle_stream.forced == stream.forced:
                    scores[index] += 3
                if self._subtitle_stream.hearingImpaired == stream.hearingImpaired:
                    scores[index] += 3
                if self._subtitle_stream.codec is not None and stream.codec is not None and \
                        self._subtitle_stream.codec == stream.codec:
                    scores[index] += 1

                # Individual title field matching
                #if self._subtitle_stream.extendedDisplayTitle is not None and stream.extendedDisplayTitle is not None and \
                #        self._subtitle_stream.extendedDisplayTitle == stream.extendedDisplayTitle:
                #    scores[index] += 5
                #if self._subtitle_stream.displayTitle is not None and stream.displayTitle is not None and \
                #        self._subtitle_stream.displayTitle == stream.displayTitle:
                #    scores[index] += 5
                if self._subtitle_stream.title is not None and stream.title is not None and \
                        self._subtitle_stream.title == stream.title:
                    scores[index] += 5

        # Logging for debugging
        logger.debug(f"Subtitle scores: {scores}, Streams: {streams}")
        return streams[scores.index(max(scores))]

    @staticmethod
    def _get_selected_streams(episode: Union[Episode, MediaPart]) -> Tuple[Optional[AudioStream], Optional[SubtitleStream]]:
        """
        Get the currently selected audio and subtitle streams for an episode or media part.

        Args:
            episode (Union[Episode, MediaPart]): The episode or media part to get streams from.

        Returns:
            Tuple[Optional[AudioStream], Optional[SubtitleStream]]: A tuple containing the selected
                audio stream and subtitle stream, or None if not selected.
        """
        audio_stream = ([a for a in episode.audioStreams() if a.selected] + [None])[0]
        subtitle_stream = ([s for s in episode.subtitleStreams() if s.selected] + [None])[0]
        return audio_stream, subtitle_stream


class NewOrUpdatedTrackChanges():
    """
    Manages track changes for newly added or updated episodes.

    This class handles the application of track changes to newly added or updated
    episodes for multiple users, and generates appropriate notifications.

    Attributes:
        _episode (Optional[Episode]): The episode being processed.
        _event_type (EventType): The type of event that triggered these changes.
        _new (bool): Whether the episode is newly added (True) or updated (False).
        _track_changes (List[TrackChanges]): List of track changes for different users.
        _description (str): Human-readable description of the changes.
        _title (str): Title for the change notification.
    """

    def __init__(self, event_type: EventType, new: bool):
        """
        Initialize a NewOrUpdatedTrackChanges instance.

        Args:
            event_type (EventType): The type of event that triggered these changes.
            new (bool): Whether the episode is newly added (True) or updated (False).
        """
        self._episode = None
        self._event_type = event_type
        self._new = new
        self._track_changes = []
        self._description = ""
        self._title = ""

    @property
    def episode_name(self) -> str:
        """
        Get a formatted name of the episode.

        Returns:
            str: The episode name in the format "Show Title (S01E02)", or an empty string if no episode.
        """
        if self._episode is None:
            return ""
        return f"{self._episode.show().title} (S{self._episode.seasonNumber:02}E{self._episode.episodeNumber:02})"

    @property
    def event_type(self) -> EventType:
        """
        Get the event type that triggered these changes.

        Returns:
            EventType: The event type.
        """
        return self._event_type

    @property
    def description(self) -> str:
        """
        Get a human-readable description of the changes.

        Returns:
            str: The description of changes.
        """
        return self._description

    @property
    def inline_description(self) -> str:
        """
        Get a single-line description of the changes.

        Returns:
            str: The description with newlines replaced by pipe separators.
        """
        return self._description.replace("\n", " | ")

    @property
    def title(self) -> str:
        """
        Get the title for the change notification.

        Returns:
            str: The title.
        """
        return self._title

    @property
    def has_changes(self) -> bool:
        """
        Check if there are any changes to apply.

        Returns:
            bool: True if there are changes for any user, False otherwise.
        """
        return sum([1 for tc in self._track_changes if tc.has_changes]) > 0

    def change_track_for_user(self, username: str, reference: Episode, episode: Episode) -> None:
        """
        Apply track changes for a specific user based on their reference episode.

        Creates a TrackChanges instance for the user, computes the necessary changes,
        applies them, and updates the description.

        Args:
            username (str): The username to apply changes for.
            reference (Episode): The reference episode with the user's preferred tracks.
            episode (Episode): The episode to apply changes to.
        """
        self._episode = episode
        track_changes = TrackChanges(username, reference, self._event_type)
        track_changes.compute([episode])
        track_changes.apply()
        self._track_changes.append(track_changes)
        self._update_description()

    def _update_description(self) -> None:
        """
        Update the description of the changes based on the episode status.

        Sets the title and description for notifications based on whether
        the episode is new or updated.
        """
        if len(self._track_changes) == 0:
            self._title = ""
            self._description = ""
            self._episode = None
            return
        event_str = "New" if self._new else "Updated"
        self._title = f"{event_str}: {self.episode_name}"
        self._description = (
            f"Episode: {self.episode_name}\n"
            f"Status: {event_str} episode\n"
            f"Updated for all users"
        )
