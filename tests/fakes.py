"""Duck-typed stand-ins for the plexapi objects the helpers under test touch.

Deliberately not plexapi types: these tests must run without a Plex server,
which is exactly what the previous suite (removed in 709cc76) could not do.
"""

import itertools

_STREAM_IDS = itertools.count(1)


class FakeSubtitleStream:
    """Duck-type of plexapi.media.SubtitleStream: the attributes TrackChanges touches."""

    def __init__(self, title="English", display_title=None, extended_display_title=None,
                 language_code="en", codec="mov_text", selected=False,
                 forced=False, hearing_impaired=False):
        self.id = next(_STREAM_IDS)
        self.title = title
        self.displayTitle = display_title if display_title is not None else title
        self.extendedDisplayTitle = (extended_display_title if extended_display_title is not None
                                     else display_title if display_title is not None else title)
        self.languageCode = language_code
        self.codec = codec
        self.selected = selected
        self.forced = forced
        self.hearingImpaired = hearing_impaired

    def __eq__(self, other):
        # plexapi objects compare by id
        return isinstance(other, FakeSubtitleStream) and self.id == other.id

    def __hash__(self):
        return hash(self.id)


class FakeAudioStream:
    """Duck-type of plexapi.media.AudioStream: the attributes TrackChanges touches."""

    def __init__(self, title="English", display_title=None, extended_display_title=None,
                 language_code="en", codec="ac3", channels=2, audio_channel_layout="stereo",
                 visual_impaired=False, selected=False):
        self.id = next(_STREAM_IDS)
        self.title = title
        self.displayTitle = display_title if display_title is not None else title
        self.extendedDisplayTitle = (extended_display_title if extended_display_title is not None
                                     else display_title if display_title is not None else title)
        self.languageCode = language_code
        self.codec = codec
        self.channels = channels
        self.audioChannelLayout = audio_channel_layout
        self.visualImpaired = visual_impaired
        self.selected = selected

    def __eq__(self, other):
        # plexapi objects compare by id
        return isinstance(other, FakeAudioStream) and self.id == other.id

    def __hash__(self):
        return hash(self.id)


class FakePart:
    def __init__(self, key="/part/1", file="/media/show/s01e01.mkv",
                 audio_streams=None, subtitle_streams=None):
        self.key = key
        self.file = file
        self.audio_streams = list(audio_streams or [])
        self.subtitle_streams = list(subtitle_streams or [])
        # Recorder state so tests can assert what apply() did without a Plex server.
        self.selected_audio_stream = None
        self.selected_subtitle_stream = None
        self.subtitle_reset_count = 0

    def audioStreams(self):
        return self.audio_streams

    def subtitleStreams(self):
        return self.subtitle_streams

    def setSelectedAudioStream(self, stream):
        self.selected_audio_stream = stream

    def setSelectedSubtitleStream(self, stream):
        self.selected_subtitle_stream = stream

    def resetSelectedSubtitleStream(self):
        self.subtitle_reset_count += 1
        self.selected_subtitle_stream = None


class FakeMedia:
    def __init__(self, parts=None):
        self.parts = parts if parts is not None else [FakePart()]


class FakeShow:
    def __init__(self, title="Some Show", labels=None):
        self.title = title
        self.labels = labels or []


class _Raises:
    """Sentinel: makes episode.show() raise, as plexapi does via NotFound."""


class FakeEpisode:
    def __init__(self, key="/library/metadata/1", added_at=None,
                 library_section_title="TV Shows", season_number=1,
                 episode_number=1, show_title="Some Show", show_key=9,
                 files=("/media/show/s01e01.mkv",), show=None, parts=None):
        self.key = key
        self.addedAt = added_at
        self.librarySectionTitle = library_section_title
        self.seasonNumber = season_number
        self.episodeNumber = episode_number
        self.grandparentTitle = show_title
        self.grandparentRatingKey = show_key
        # Real Episodes carry both: parentIndex is the raw attribute, seasonNumber
        # is a cached_data_property derived from it that can hit the network.
        self.parentIndex = season_number
        if parts is None:
            parts = [FakePart(key=f"/part/{i}", file=f) for i, f in enumerate(files)]
        self.parts = parts
        self.media = [FakeMedia(parts)]
        self._show = show if show is not None else FakeShow(title=show_title or "")

    def iterParts(self):
        for media in self.media:
            for part in media.parts:
                yield part

    def reload(self):
        # No-op: TrackChanges.compute() reloads every target episode before matching.
        pass

    def audioStreams(self):
        # Mirrors plexapi Episode.audioStreams(): concatenation of the part stream lists.
        return [s for part in self.parts for s in part.audioStreams()]

    def subtitleStreams(self):
        # Mirrors plexapi Episode.subtitleStreams(): concatenation of the part stream lists.
        return [s for part in self.parts for s in part.subtitleStreams()]

    def show(self):
        if isinstance(self._show, _Raises):
            raise RuntimeError("simulated plexapi NotFound")
        return self._show
