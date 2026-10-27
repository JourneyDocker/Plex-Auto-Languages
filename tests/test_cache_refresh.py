from datetime import datetime, timedelta
from threading import RLock
from types import SimpleNamespace

from plex_auto_languages.alerts.status import PlexStatus, SCAN_REFRESH_COOLDOWN
from plex_auto_languages.plex_server import PlexServer
from plex_auto_languages.plex_server_cache import PlexServerCache
from tests.fakes import FakeEpisode, FakeMedia, FakePart


def _episode(key, part_keys):
    episode = FakeEpisode(key=key)
    episode.media = [FakeMedia([FakePart(key=k) for k in part_keys])]
    return episode


def _cache(episode_parts, episodes):
    plex = object.__new__(PlexServer)
    plex.config = {"ignore_filepatterns": [""]}
    plex.iter_episodes = lambda: iter(episodes)
    cache = object.__new__(PlexServerCache)
    cache._plex = plex
    cache._lock = RLock()
    cache._is_refreshing = False
    cache._last_refresh = datetime.fromtimestamp(0)
    cache.episode_parts = dict(episode_parts)
    cache.save = lambda force=False: None
    return cache


def test_refresh_returns_added_and_updated_and_swaps_parts():
    cache = _cache(
        {
            "/library/metadata/1": ["/part/old"],  # changes below -> updated
            "/library/metadata/3": ["/part/b"],    # unchanged below -> skipped
        },
        [
            _episode("/library/metadata/1", ["/part/new"]),  # changed -> updated
            _episode("/library/metadata/2", ["/part/a"]),    # new -> added
            _episode("/library/metadata/3", ["/part/b"]),    # unchanged -> skipped
        ],
    )

    added, updated = cache.refresh_library_cache()

    assert [r.key for r in added] == ["/library/metadata/2"]
    assert [r.key for r in updated] == ["/library/metadata/1"]
    assert cache.episode_parts["/library/metadata/3"] == ["/part/b"]
    assert cache.episode_parts["/library/metadata/2"] == ["/part/a"]


def test_refresh_diffs_against_snapshot_not_live_dict():
    # A metadataState consumer mutates the live dict mid-refresh (concurrent
    # did_episode_parts_change); the diff must still compare against the parts
    # recorded at refresh start, or the change would be missed.
    cache = _cache(
        {"/library/metadata/1": ["/part/old"]},
        [_episode("/library/metadata/1", ["/part/new"])],
    )
    original_iter = cache._plex.iter_episodes
    cache._plex.iter_episodes = lambda: _mutate_mid_iteration(cache, original_iter)

    _, updated = cache.refresh_library_cache()

    assert [r.key for r in updated] == ["/library/metadata/1"]


def _mutate_mid_iteration(cache, original_iter):
    yield next(original_iter())
    # Simulate did_episode_parts_change() updating the live cache while the
    # refresh is still iterating.
    cache.episode_parts["/library/metadata/1"] = ["/part/new"]


def test_refresh_is_reentrant_guard():
    cache = _cache({}, [])
    cache._is_refreshing = True

    added, updated = cache.refresh_library_cache()

    assert (added, updated) == ([], [])


def _status_plex(calls, refresh_library_on_scan=True, last_refresh=None):
    plex = object.__new__(PlexServer)
    plex.config = {"refresh_library_on_scan": refresh_library_on_scan}
    plex.cache = SimpleNamespace(
        last_refresh=last_refresh or datetime.fromtimestamp(0),
        refresh_library_cache=lambda: (calls.append("full"), ([], []))[1],
    )
    plex.get_recently_added_episode_refs = lambda minutes=5: (calls.append("cheap"), [])[1]
    return plex


def _process_status(plex):
    PlexStatus({"title": "Library scan complete"}).process(plex)


def test_scan_within_cooldown_uses_cheap_query():
    calls = []
    plex = _status_plex(calls, last_refresh=datetime.now())

    _process_status(plex)

    assert calls == ["cheap"]


def test_scan_after_cooldown_runs_full_refresh():
    calls = []
    plex = _status_plex(calls, last_refresh=datetime.now() - SCAN_REFRESH_COOLDOWN - timedelta(seconds=1))

    _process_status(plex)

    assert calls == ["full"]


def test_scan_never_full_refreshes_when_disabled():
    calls = []
    plex = _status_plex(calls, refresh_library_on_scan=False, last_refresh=datetime.now())

    _process_status(plex)

    assert calls == ["cheap"]
