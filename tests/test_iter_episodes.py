from plex_auto_languages.plex_server import PlexServer
from tests.fakes import FakeEpisode


class FakeSection:
    def __init__(self, title, episodes):
        self.title = title
        self._episodes = episodes

    def search(self, libtype=None, sort=None, container_start=0,
               container_size=None, maxresults=None):
        return self._episodes[container_start:container_start + container_size]


def _server(sections):
    server = object.__new__(PlexServer)
    server.get_show_sections = lambda: sections
    return server


def test_iter_episodes_stamps_the_owning_section_title():
    # Episodes from a section search carry no librarySectionTitle of their own:
    # it lives on the MediaContainer. Reading it unstamped makes plexapi issue a
    # full metadata reload per episode (base.py:657), which on a 65,925-episode
    # library is 65,925 requests inside the refresh lock.
    episodes = [FakeEpisode(key=f"/library/metadata/{i}", library_section_title=None)
                for i in range(3)]
    server = _server([FakeSection("TV Shows", episodes)])

    out = list(server.iter_episodes(page_size=2))

    assert len(out) == 3
    assert [e.librarySectionTitle for e in out] == ["TV Shows"] * 3


def test_iter_episodes_stamps_each_section_separately():
    tv = [FakeEpisode(key="/library/metadata/1", library_section_title=None)]
    sports = [FakeEpisode(key="/library/metadata/2", library_section_title=None)]
    server = _server([FakeSection("TV Shows", tv), FakeSection("Sports", sports)])

    out = list(server.iter_episodes(page_size=10))

    assert [e.librarySectionTitle for e in out] == ["TV Shows", "Sports"]


def test_iter_episodes_paginates_across_pages():
    episodes = [FakeEpisode(key=f"/library/metadata/{i}", library_section_title=None)
                for i in range(5)]
    server = _server([FakeSection("TV Shows", episodes)])

    out = list(server.iter_episodes(page_size=2))

    assert [e.key for e in out] == [f"/library/metadata/{i}" for i in range(5)]
