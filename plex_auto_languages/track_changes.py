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
        _audio_index (Optional[int]): Position of the selected audio stream within the reference
            episode's filtered audio candidate list; tie-breaker for duplicate track names.
        _subtitle_index (Optional[int]): Position of the selected subtitle stream within the
            reference episode's filtered subtitle candidate list; tie-breaker for duplicates.
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
        # Positions of the selected streams within their filtered candidate lists, used only to
        # break score ties between duplicate track names (see _select_best).
        self._audio_index = self._reference_index(
            self._audio_stream,
            self._filter_audio_streams(reference.audioStreams(), self._audio_stream))
        self._subtitle_index = self._reference_index(
            self._subtitle_stream,
            self._filter_subtitle_streams(reference.subtitleStreams(),
                                          self._subtitle_stream, self._audio_stream))
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
        logger.debug(f"[Language Update] Checking language update for show '{self._reference.show().title}' "
                     f"and user '{self._username}' based on episode: 'S{self._reference.seasonNumber:02}E{self._reference.episodeNumber:02}'")
        self._changes = []
        reference_has_subtitle_streams = len(self._reference.subtitleStreams()) > 0
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

                # If no matching subtitle found, only reset to None when the reference had NO subtitle selected.
                # If the reference episode has no subtitle streams at all, do not propagate "None" to other episodes.
                # This avoids disabling subtitles on episodes that do have subtitle streams while the reference episode
                # simply has burned-in subtitles or no subtitle track available.
                
                if current_subtitle_stream is not None and matching_subtitle_stream is None:
                    if self._subtitle_stream is None:
                        if reference_has_subtitle_streams:
                            # Reference has subtitle streams and subtitles are explicitly off -> clear current subtitle.
                            self._changes.append((episode, part, SubtitleStream.STREAMTYPE, None))
                        else:
                            # Reference has no subtitle streams at all -> do not propagate "None".
                            pass
                    elif self.is_forced_subtitle(self._subtitle_stream):
                        # Reference uses forced subtitles, but this part has no matching forced subtitle.
                        # Clear the current subtitle instead of keeping a regular subtitle from the same language.
                        self._changes.append((episode, part, SubtitleStream.STREAMTYPE, None))
                    else:
                        # Reference had a regular subtitle but no matching subtitle was found for this part.
                        # Keep the current subtitle to avoid disabling subtitles unexpectedly.
                        pass

                if matching_subtitle_stream is not None and \
                        (current_subtitle_stream is None or matching_subtitle_stream.id != current_subtitle_stream.id):
                    if current_audio_stream is not None and current_audio_stream.title is not None and \
                            "commentary" in current_audio_stream.title.lower() and matching_audio_stream is None:
                        # if the changed stream was commentary but this ep has none, then don't touch subs
                        logger.debug(f"[Language Update] Skipping subtitle changes for show '{episode.show().title}' "
                                     f"episode 'S{episode.seasonNumber:02}E{episode.episodeNumber:02}' "
                                     f"and user '{self.username}'")
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
            logger.debug(f"[Language Update] No changes to perform for show '{self._reference.show().title}' and user '{self._username}'")
            return
        logger.debug(f"[Language Update] Performing {len(self._changes)} change(s) for show '{self._reference.show().title}'")
        for episode, part, stream_type, new_stream in self._changes:
            stream_type_name = "audio" if stream_type == AudioStream.STREAMTYPE else "subtitle"
            logger.debug(f"[Language Update] Updating {stream_type_name} stream of show '{episode.show().title}' "
                         f"episode 'S{episode.seasonNumber:02}E{episode.episodeNumber:02}' to "
                         f"'{(new_stream.extendedDisplayTitle or new_stream.title or 'Unknown') if new_stream else 'Disabled'}'")
            try:
                if stream_type == AudioStream.STREAMTYPE:
                    part.setSelectedAudioStream(new_stream)
                elif stream_type == SubtitleStream.STREAMTYPE and new_stream is None:
                    part.resetSelectedSubtitleStream()
                elif stream_type == SubtitleStream.STREAMTYPE:
                    part.setSelectedSubtitleStream(new_stream)
            except Exception as e:
                logger.error(f"[Language Update] Failed to update {stream_type_name} stream for episode "
                             f"'S{episode.seasonNumber:02}E{episode.episodeNumber:02}' of show '{episode.show().title}': {e}")
        # Clear changes and references to free memory
        self._changes.clear()
        self._reference = None
        self._audio_stream = None
        self._subtitle_stream = None
        self._audio_index = None
        self._subtitle_index = None
        self._changes = None

    def _is_episode_after(self, episode: Episode) -> bool:
        """
        Check if an episode comes after the reference episode.

        Args:
            episode (Episode): The episode to check.

        Returns:
            bool: True if the episode comes after the reference, False otherwise.
        """
        if self._reference.seasonNumber is None or self._reference.episodeNumber is None:
            return False
        if episode.seasonNumber is None or episode.episodeNumber is None:
            return False
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

        # Build subtitles text cleanly
        if self._subtitle_stream is not None:
            sub_title = (
                f"{self._subtitle_stream.displayTitle} "
                f"({self._subtitle_stream.extendedDisplayTitle or self._subtitle_stream.title or 'Unknown'})"
            )
        else:
            sub_title = "None"

        # Build description safely and clearly
        self._description = (
            f"Show: {self._reference.show().title}\n"
            f"User: {self._username}\n"
            f"Audio: {self._audio_stream.displayTitle if self._audio_stream is not None else 'None'}\n"
            f"Subtitles: {sub_title}\n"
            f"Updated episodes: {nb_updated}/{nb_total} ({range_str})"
        )

    def _match_audio_stream(self, audio_streams: List[AudioStream]) -> Optional[AudioStream]:
        """
        Find the best matching audio stream from a list of available streams.

        Matches based on language code, descriptive terms, visual impaired flag, codec,
        channel layout, and title similarity to the reference audio stream. When several
        candidates tie at the top score (for example duplicate track names), the candidate
        at the same position within the filtered list as the reference's selected stream
        is preferred.

        Args:
            audio_streams (List[AudioStream]): The list of available audio streams.

        Returns:
            Optional[AudioStream]: The best matching audio stream, or None if no match found.
        """
        # The reference stream can be 'None'
        if self._audio_stream is None:
            return None

        # Check if streams aren't differentiated
        ambiguous = all(s.title == audio_streams[0].title for s in audio_streams)

        streams = self._filter_audio_streams(audio_streams, self._audio_stream)
        if streams is None or len(streams) == 0:
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
            if self._audio_stream.extendedDisplayTitle is not None and stream.extendedDisplayTitle is not None and \
                    self._audio_stream.extendedDisplayTitle == stream.extendedDisplayTitle:
                scores[index] += 5
            if self._audio_stream.displayTitle is not None and stream.displayTitle is not None and \
                    self._audio_stream.displayTitle == stream.displayTitle:
                scores[index] += 5
            if self._audio_stream.title is not None and stream.title is not None and \
                    self._audio_stream.title == stream.title:
                scores[index] += 5

        # Logging for debugging; the position within the filtered list disambiguates duplicate names
        score_str = ", ".join(
            f"{(stream.extendedDisplayTitle or stream.title or 'Unknown')}@{position}={score}"
            for position, (stream, score) in enumerate(zip(streams, scores)))
        logger.debug(f"[Language Update] Audio scores: {score_str}")
        return self._select_best(streams, scores, self._audio_index)

    @staticmethod
    def is_forced_subtitle(stream: SubtitleStream) -> bool:
        """
        Check whether a subtitle stream is a forced (dialog) track.

        A track is considered forced when Plex marks it as forced, or when one of its
        title fields mentions "forced".

        Args:
            stream (SubtitleStream): The subtitle stream to check.

        Returns:
            bool: True when the stream is forced.
        """
        title = getattr(stream, "title", None)
        display_title = getattr(stream, "displayTitle", None)
        extended_display_title = getattr(stream, "extendedDisplayTitle", None)
        forced_flag = bool(getattr(stream, "forced", False))
    
        searchable_text = " ".join([
            title or "",
            display_title or "",
            extended_display_title or "",
        ]).lower()
    
        forced_from_title = (
            "forced" in searchable_text
        )
    
        result = forced_flag or forced_from_title
        return result
        
    def _match_subtitle_stream(self, subtitle_streams: List[SubtitleStream]) -> Optional[SubtitleStream]:
        """
        Find the best matching subtitle stream from a list of available streams.

        Matches based on language code, forced flag, hearing impaired flag,
        codec, and title similarity to the reference subtitle stream. When several
        candidates tie at the top score (for example duplicate track names), the candidate
        at the same position within the filtered list as the reference's selected stream
        is preferred.

        Args:
            subtitle_streams (List[SubtitleStream]): The list of available subtitle streams.

        Returns:
            Optional[SubtitleStream]: The best matching subtitle stream, or None if no match found.
        """
        # If there is neither a reference subtitle nor a reference audio stream, there is
        # nothing to match against. Otherwise filter to the reference language, keeping only
        # forced subtitles when the reference has subtitles off, and only hearing impaired
        # subtitles when the reference uses them.
        streams = self._filter_subtitle_streams(subtitle_streams, self._subtitle_stream, self._audio_stream)
        if streams is None or len(streams) == 0:
            return None

        if len(streams) == 1:
            return streams[0]

        # Score the remaining streams based on attributes
        scores = [0] * len(streams)
        for index, stream in enumerate(streams):
            if self._subtitle_stream is not None:
                if self.is_forced_subtitle(self._subtitle_stream) == self.is_forced_subtitle(stream):
                    scores[index] += 3
                if self._subtitle_stream.hearingImpaired == stream.hearingImpaired:
                    scores[index] += 3
                if self._subtitle_stream.codec is not None and stream.codec is not None and \
                        self._subtitle_stream.codec == stream.codec:
                    scores[index] += 1

                # Individual title field matching
                if self._subtitle_stream.extendedDisplayTitle is not None and stream.extendedDisplayTitle is not None and \
                        self._subtitle_stream.extendedDisplayTitle == stream.extendedDisplayTitle:
                    scores[index] += 5
                if self._subtitle_stream.displayTitle is not None and stream.displayTitle is not None and \
                        self._subtitle_stream.displayTitle == stream.displayTitle:
                    scores[index] += 5
                if self._subtitle_stream.title is not None and stream.title is not None and \
                        self._subtitle_stream.title == stream.title:
                    scores[index] += 5

        # Logging for debugging; the position within the filtered list disambiguates duplicate names
        score_str = ", ".join(
            f"{(stream.extendedDisplayTitle or stream.title or 'Unknown')}@{position}={score}"
            for position, (stream, score) in enumerate(zip(streams, scores)))
        logger.debug(f"[Language Update] Subtitle scores: {score_str}")
        return self._select_best(streams, scores, self._subtitle_index)

    @staticmethod
    def _get_stream_title(stream) -> str:
        """
        Get the most specific title available for a stream, lower-cased.

        Args:
            stream: An audio or subtitle stream.

        Returns:
            str: The lower-cased extended display title, display title, or title (empty string
                when all are missing).
        """
        return (stream.extendedDisplayTitle or
                stream.displayTitle or
                stream.title or "").lower()

    @staticmethod
    def _contains_descriptive_terms(title: str) -> bool:
        """
        Check if a stream title contains terms indicating a descriptive track.

        Args:
            title (str): The lower-cased stream title.

        Returns:
            bool: True when the title contains a descriptive-track term.
        """
        descriptive_terms = [
            "commentary", "description", "descriptive",
            "narration", "narrative", "described"
        ]
        return any(term in title for term in descriptive_terms)

    @classmethod
    def _filter_audio_streams(cls, audio_streams: List[AudioStream],
                              reference_audio: Optional[AudioStream]) -> Optional[List[AudioStream]]:
        """
        Filter candidate audio streams for the reference audio stream.

        Keeps streams with the same language code as the reference, then narrows to
        visual-impaired (or non-visual-impaired) and descriptive (or non-descriptive) tracks,
        mirroring the reference track. Logic is unchanged from the pre-refactor matcher.

        Args:
            audio_streams (List[AudioStream]): All available audio streams (raw, unfiltered).
            reference_audio (Optional[AudioStream]): The reference audio stream.

        Returns:
            Optional[List[AudioStream]]: The filtered candidate list, or None when there is no
                reference audio stream to match against.
        """
        if reference_audio is None:
            return None

        # We only want streams with the same language code
        streams = [s for s in audio_streams if s.languageCode == reference_audio.languageCode]

        # First, try to match visualImpaired flag if available
        try:
            # Check if the reference is a visual impaired track
            if hasattr(reference_audio, 'visualImpaired') and reference_audio.visualImpaired:
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
        ref_title = cls._get_stream_title(reference_audio)
        if cls._contains_descriptive_terms(ref_title):
            # Keep only descriptive tracks if reference is descriptive
            descriptive_streams = [s for s in streams if cls._contains_descriptive_terms(cls._get_stream_title(s))]
            if descriptive_streams:
                streams = descriptive_streams
        else:
            # Filter out descriptive tracks if reference is not descriptive
            non_descriptive_streams = [s for s in streams if not cls._contains_descriptive_terms(cls._get_stream_title(s))]
            if non_descriptive_streams:
                streams = non_descriptive_streams

        return streams

    @classmethod
    def _filter_subtitle_streams(cls, subtitle_streams: List[SubtitleStream],
                                 reference_subtitle: Optional[SubtitleStream],
                                 reference_audio: Optional[AudioStream]) -> Optional[List[SubtitleStream]]:
        """
        Filter candidate subtitle streams for the reference subtitle stream.

        Keeps streams with the same language code as the reference subtitle (or, when the
        reference has no subtitle selected, the reference audio), then narrows to forced-only
        and hearing-impaired tracks, mirroring the reference. Logic is unchanged from the
        pre-refactor matcher.

        Args:
            subtitle_streams (List[SubtitleStream]): All available subtitle streams (raw, unfiltered).
            reference_subtitle (Optional[SubtitleStream]): The reference subtitle stream.
            reference_audio (Optional[AudioStream]): The reference audio stream, used when the
                reference has no subtitle selected.

        Returns:
            Optional[List[SubtitleStream]]: The filtered candidate list, or None when there is
                neither a reference subtitle nor a reference audio stream to match against.
        """
        if reference_subtitle is None:
            if reference_audio is None:
                return None
            match_forced_only = True
            match_hearing_impaired_only = False
            language_code = reference_audio.languageCode
        else:
            match_forced_only = cls.is_forced_subtitle(reference_subtitle)
            match_hearing_impaired_only = reference_subtitle.hearingImpaired
            language_code = reference_subtitle.languageCode

        # We only want streams with the same language code
        streams = [s for s in subtitle_streams if s.languageCode == language_code]
        if match_forced_only:
            streams = [s for s in streams if cls.is_forced_subtitle(s)]
        if match_hearing_impaired_only:
            streams = [s for s in streams if s.hearingImpaired]
        return streams

    @staticmethod
    def _select_best(streams: List, scores: List[int], reference_index: Optional[int]):
        """
        Pick the best stream from scored candidates.

        The highest score always wins. When several candidates tie at the top score (for
        example duplicate track names), the candidate that sits at the same position within
        the filtered candidate list as the reference's selected stream is preferred, so a
        user's deliberate pick of one duplicate is preserved across episodes, including when
        the track layout shifts. Otherwise the first tied candidate is kept (previous behavior).

        Args:
            streams (List): The scored candidate streams, in filtered-list order.
            scores (List[int]): The score per candidate, aligned with `streams`.
            reference_index (Optional[int]): Position of the reference's selected stream within
                its own filtered candidate list, or None.

        Returns:
            The best matching stream.
        """
        best = max(scores)
        tied = [s for s, sc in zip(streams, scores) if sc == best]
        if len(tied) == 1:
            return tied[0]
        if reference_index is not None and reference_index < len(streams):
            candidate = streams[reference_index]
            if candidate in tied:
                return candidate
        return tied[0]

    @staticmethod
    def _reference_index(selected_stream, filtered_streams: Optional[List]) -> Optional[int]:
        """
        Get the position of the selected stream within a filtered candidate list.

        Args:
            selected_stream: The selected stream, or None.
            filtered_streams (Optional[List]): The filtered candidate list, or None.

        Returns:
            Optional[int]: The 0-based position, or None when it cannot be determined.
        """
        if selected_stream is None or filtered_streams is None:
            return None
        for index, stream in enumerate(filtered_streams):
            if stream.id == selected_stream.id:
                return index
        return None

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
        return len(self._track_changes) > 0

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
        changes_were_made = track_changes.has_changes
        track_changes.apply()
        if changes_were_made:
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