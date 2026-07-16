from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class EpisodeRef:
    """The subset of an Episode that the post-refresh consumers actually read.

    refresh_library_cache() used to hand back live plexapi Episode objects at
    roughly 12KB each, so a bulk part-key churn retained the whole library
    (~790MB on a 65,906-episode server) and got the process OOM-killed. These
    measure ~356 bytes. Every field is already loaded on the Episode during the
    refresh, so building one costs no extra requests.

    Note show_title comes from grandparentTitle, which is NOT always the same as
    show().title: a show with an empty title reports grandparentTitle = None.
    """

    key: str
    added_at: datetime | None
    library_section_title: str | None
    season_number: int | None
    episode_number: int | None
    show_title: str | None
    show_key: int | None
    part_files: tuple[str, ...] = field(default=())

    @classmethod
    def from_episode(cls, episode, collect_part_files: bool = False) -> "EpisodeRef":
        """Build a ref from an already-loaded Episode.

        Args:
            episode: A plexapi Episode that has already been loaded.
            collect_part_files: Whether to record media file paths. Only needed
                when ignore_filepatterns is configured; the shipped default is
                [""], which disables the check entirely, so the paths would be
                retained for nothing.
        """
        part_files: tuple[str, ...] = ()
        if collect_part_files:
            part_files = tuple(
                part.file for part in episode.iterParts() if getattr(part, "file", None)
            )
        return cls(
            key=episode.key,
            added_at=getattr(episode, "addedAt", None),
            library_section_title=getattr(episode, "librarySectionTitle", None),
            # parentIndex, not seasonNumber: the latter is a cached_data_property
            # that falls back to fetching the season over the network when
            # parentIndex is neither int nor None (utils.cast yields NaN on a
            # malformed attribute). getattr's default only swallows AttributeError,
            # so a NotFound from that fetch would abort the whole refresh. This
            # runs 65,906 times; it must not touch the network.
            season_number=getattr(episode, "parentIndex", None),
            episode_number=getattr(episode, "episodeNumber", None),
            show_title=getattr(episode, "grandparentTitle", None),
            show_key=getattr(episode, "grandparentRatingKey", None),
            part_files=part_files,
        )
