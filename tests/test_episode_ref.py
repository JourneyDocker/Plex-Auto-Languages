from datetime import datetime

import pytest

from plex_auto_languages.episode_ref import EpisodeRef
from tests.fakes import FakeEpisode


def test_from_episode_maps_every_field():
    when = datetime(2026, 7, 15, 12, 0, 0)
    ep = FakeEpisode(key="/library/metadata/5", added_at=when,
                     library_section_title="TV Shows", season_number=2, episode_number=7,
                     show_title="Deli Boys", show_key=9)
    ref = EpisodeRef.from_episode(ep)
    assert ref.key == "/library/metadata/5"
    assert ref.added_at == when
    assert ref.library_section_title == "TV Shows"
    assert ref.season_number == 2
    assert ref.episode_number == 7
    assert ref.show_title == "Deli Boys"
    assert ref.show_key == 9


def test_part_files_omitted_by_default():
    ep = FakeEpisode(files=("/media/a.mkv", "/media/b.mkv"))
    assert EpisodeRef.from_episode(ep).part_files == ()


def test_part_files_collected_when_requested():
    ep = FakeEpisode(files=("/media/a.mkv", "/media/b.mkv"))
    ref = EpisodeRef.from_episode(ep, collect_part_files=True)
    assert ref.part_files == ("/media/a.mkv", "/media/b.mkv")


def test_none_show_title_is_preserved_not_coerced():
    # KidTube episodes (show 258471) report grandparentTitle = None. The ref must
    # carry the None through rather than inventing a placeholder; formatting is
    # format_ref_name's job.
    ep = FakeEpisode(show_title=None)
    assert EpisodeRef.from_episode(ep).show_title is None


def test_from_episode_does_not_call_show():
    # Building a ref must not trigger a Plex fetch: this runs 65,906 times.
    class Exploding(FakeEpisode):
        def show(self):
            raise AssertionError("from_episode must not call show()")

    assert EpisodeRef.from_episode(Exploding()).show_title == "Some Show"


def test_ref_is_frozen():
    ref = EpisodeRef.from_episode(FakeEpisode())
    with pytest.raises(Exception):
        ref.key = "/library/metadata/999"
