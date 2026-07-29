"""Duck-typed stand-ins for the plexapi objects the helpers under test touch.

Deliberately not plexapi types: these tests must run without a Plex server,
which is exactly what the previous suite (removed in 709cc76) could not do.
"""


class FakePart:
    def __init__(self, key="/part/1", file="/media/show/s01e01.mkv"):
        self.key = key
        self.file = file


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
                 files=("/media/show/s01e01.mkv",), show=None):
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
        self.media = [FakeMedia([FakePart(key=f"/part/{i}", file=f) for i, f in enumerate(files)])]
        self._show = show if show is not None else FakeShow(title=show_title or "")

    def iterParts(self):
        for media in self.media:
            for part in media.parts:
                yield part

    def show(self):
        if isinstance(self._show, _Raises):
            raise RuntimeError("simulated plexapi NotFound")
        return self._show
