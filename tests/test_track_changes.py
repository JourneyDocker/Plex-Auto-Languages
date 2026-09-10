"""
Tests for TrackChanges track matching, focused on duplicate track names (issue #110).

The fakes are duck-typed, so no Plex server is required. The scenarios cover:

- duplicate subtitle names: the user's pick of one duplicate (first or second of the pair)
  is preserved on other episodes;
- the reporter's forced-track layout shift, where the same pair sits at different raw
  indices in each episode and the reference position within the filtered candidate list
  (not the raw index) must be used;
- duplicate audio names using the same tie-break;
- score priority: a genuinely higher score beats the reference position, and reversed
  pair order is resolved by target position;
- out-of-range reference position falls back to the first top-scoring stream;
- no changes computed when neither the reference nor the target has a subtitle selected.
"""

from plex_auto_languages.constants import EventType
from plex_auto_languages.track_changes import TrackChanges
from tests.fakes import FakeAudioStream, FakeEpisode, FakePart, FakeSubtitleStream

USERNAME = "alice"


def make_episode(audio, subtitles, episode_number=1):
    """Build a single-part episode whose part owns the given stream objects.

    Returns the (episode, part) pair so tests can assert on the part's recorder state.
    """
    part = FakePart(audio_streams=list(audio), subtitle_streams=list(subtitles))
    episode = FakeEpisode(episode_number=episode_number, parts=[part])
    return episode, part


def compute(reference, target):
    """Run the full TrackChanges flow over a single target episode (no apply)."""
    track_changes = TrackChanges(USERNAME, reference, EventType.PLAY_OR_ACTIVITY)
    track_changes.compute([target])
    return track_changes


def test_duplicate_subtitles_reference_second_selected_selects_target_second():
    # Regression scenario from issue #110: the reference's second of an identically named
    # pair must be propagated, not the first.
    ref_audio = FakeAudioStream(title="English", selected=True)
    ref_sub_first = FakeSubtitleStream(title="English (PGS)")
    ref_sub_second = FakeSubtitleStream(title="English (PGS)", selected=True)
    reference, _ = make_episode([ref_audio], [ref_sub_first, ref_sub_second])

    tgt_audio = FakeAudioStream(title="English", selected=True)
    tgt_sub_first = FakeSubtitleStream(title="English (PGS)", selected=True)
    tgt_sub_second = FakeSubtitleStream(title="English (PGS)")
    target, target_part = make_episode([tgt_audio], [tgt_sub_first, tgt_sub_second])

    track_changes = compute(reference, target)
    assert track_changes.has_changes
    track_changes.apply()
    assert target_part.selected_subtitle_stream is tgt_sub_second


def test_duplicate_subtitles_reference_first_selected_selects_target_first():
    ref_audio = FakeAudioStream(title="English", selected=True)
    ref_sub_first = FakeSubtitleStream(title="English (PGS)", selected=True)
    ref_sub_second = FakeSubtitleStream(title="English (PGS)")
    reference, _ = make_episode([ref_audio], [ref_sub_first, ref_sub_second])

    tgt_audio = FakeAudioStream(title="English", selected=True)
    tgt_sub_first = FakeSubtitleStream(title="English (PGS)")
    tgt_sub_second = FakeSubtitleStream(title="English (PGS)", selected=True)
    target, target_part = make_episode([tgt_audio], [tgt_sub_first, tgt_sub_second])

    track_changes = compute(reference, target)
    assert track_changes.has_changes
    track_changes.apply()
    assert target_part.selected_subtitle_stream is tgt_sub_first


def test_forced_track_shifted_layout_preserves_duplicate_pick():
    # The reporter's example: the reference episode has a forced track that the target
    # lacks, so the duplicate pair sits at raw indices 4/5 in the reference and 3/4 in
    # the target. The reference's second of the pair (raw 5) was selected, so the
    # target's second of the pair (raw 4) must be selected.
    ref_audio = FakeAudioStream(title="English", selected=True)
    reference_subs = [
        FakeSubtitleStream(title="Français", language_code="fr"),        # raw 0
        FakeSubtitleStream(title="Deutsch", language_code="de"),         # raw 1
        FakeSubtitleStream(title="Español", language_code="es"),         # raw 2
        FakeSubtitleStream(title="Castellano (Forced)", language_code="es", forced=True),  # raw 3
        FakeSubtitleStream(title="English (PGS)"),                       # raw 4
        FakeSubtitleStream(title="English (PGS)", selected=True),        # raw 5
    ]
    reference, _ = make_episode([ref_audio], reference_subs)

    tgt_audio = FakeAudioStream(title="English", selected=True)
    tgt_sub_first = FakeSubtitleStream(title="English (PGS)", selected=True)
    target_subs = [
        FakeSubtitleStream(title="Français", language_code="fr"),        # raw 0
        FakeSubtitleStream(title="Deutsch", language_code="de"),         # raw 1
        FakeSubtitleStream(title="Español", language_code="es"),         # raw 2
        tgt_sub_first,                                                    # raw 3
        FakeSubtitleStream(title="English (PGS)"),                       # raw 4
    ]
    target, target_part = make_episode([tgt_audio], target_subs)

    track_changes = compute(reference, target)
    assert track_changes.has_changes
    track_changes.apply()
    assert target_part.selected_subtitle_stream is target_subs[4]


def test_duplicate_audio_reference_second_selected_selects_target_second():
    # Audio duplicates use the same tie-break as subtitles.
    ref_sub = FakeSubtitleStream(title="English", selected=True)
    ref_audio_first = FakeAudioStream(title="English")
    ref_audio_second = FakeAudioStream(title="English", selected=True)
    reference, _ = make_episode([ref_audio_first, ref_audio_second], [ref_sub])

    tgt_sub = FakeSubtitleStream(title="English", selected=True)
    tgt_audio_first = FakeAudioStream(title="English", selected=True)
    tgt_audio_second = FakeAudioStream(title="English")
    target, target_part = make_episode([tgt_audio_first, tgt_audio_second], [tgt_sub])

    track_changes = compute(reference, target)
    assert track_changes.has_changes
    track_changes.apply()
    assert target_part.selected_audio_stream is tgt_audio_second


def test_scores_not_tied_score_wins_over_reference_position():
    # A genuine score difference (codec) must beat the reference position, which here
    # points at the weaker candidate.
    ref_audio = FakeAudioStream(title="English", selected=True)
    ref_sub_first = FakeSubtitleStream(title="English (PGS)", codec="mov_text", selected=True)
    ref_sub_second = FakeSubtitleStream(title="English (PGS)", codec="mov_text")
    reference, _ = make_episode([ref_audio], [ref_sub_first, ref_sub_second])

    tgt_audio = FakeAudioStream(title="English", selected=True)
    # Target's first candidate is a worse codec match than the second one.
    tgt_sub_first = FakeSubtitleStream(title="English (PGS)", codec="webvtt", selected=True)
    tgt_sub_second = FakeSubtitleStream(title="English (PGS)", codec="mov_text")
    target, target_part = make_episode([tgt_audio], [tgt_sub_first, tgt_sub_second])

    track_changes = compute(reference, target)
    assert track_changes.has_changes
    track_changes.apply()
    assert target_part.selected_subtitle_stream is tgt_sub_second


def test_reversed_pair_order_tie_break_uses_target_position():
    # With identical names the tie-break is by position within the filtered list, so a
    # reversed layout resolves to the target's first candidate when the reference pick
    # was its first.
    ref_audio = FakeAudioStream(title="English", selected=True)
    ref_sub_first = FakeSubtitleStream(title="English (PGS)", selected=True)
    ref_sub_second = FakeSubtitleStream(title="English (PGS)")
    reference, _ = make_episode([ref_audio], [ref_sub_first, ref_sub_second])

    tgt_audio = FakeAudioStream(title="English", selected=True)
    # Reversed order: the stream that was second in the reference comes first here.
    tgt_sub_reversed_first = FakeSubtitleStream(title="English (PGS)")
    tgt_sub_reversed_second = FakeSubtitleStream(title="English (PGS)", selected=True)
    target, target_part = make_episode([tgt_audio],
                                       [tgt_sub_reversed_first, tgt_sub_reversed_second])

    track_changes = compute(reference, target)
    assert track_changes.has_changes
    track_changes.apply()
    assert target_part.selected_subtitle_stream is tgt_sub_reversed_first


def test_reference_position_out_of_range_falls_back_to_first():
    # The reference picked the third of three duplicates; the target only has two.
    # The tie-break must not crash and must fall back to the first top-scoring stream.
    ref_audio = FakeAudioStream(title="English", selected=True)
    reference_subs = [
        FakeSubtitleStream(title="English (PGS)"),
        FakeSubtitleStream(title="English (PGS)"),
        FakeSubtitleStream(title="English (PGS)", selected=True),
    ]
    reference, _ = make_episode([ref_audio], reference_subs)

    tgt_audio = FakeAudioStream(title="English", selected=True)
    tgt_sub_first = FakeSubtitleStream(title="English (PGS)")
    tgt_sub_second = FakeSubtitleStream(title="English (PGS)", selected=True)
    target, target_part = make_episode([tgt_audio], [tgt_sub_first, tgt_sub_second])

    track_changes = compute(reference, target)
    assert track_changes.has_changes
    track_changes.apply()
    assert target_part.selected_subtitle_stream is tgt_sub_first


def test_no_subtitle_selected_anywhere_no_changes():
    # Reference has subtitle streams but none selected (subtitles off), and the target
    # has none selected either: nothing must change and no reset must be issued.
    ref_audio = FakeAudioStream(title="English", selected=True)
    reference, _ = make_episode([ref_audio], [FakeSubtitleStream(title="English")])

    tgt_audio = FakeAudioStream(title="English", selected=True)
    target, target_part = make_episode([tgt_audio], [FakeSubtitleStream(title="English")])

    track_changes = compute(reference, target)
    assert not track_changes.has_changes
    track_changes.apply()
    assert target_part.selected_subtitle_stream is None
    assert target_part.selected_audio_stream is None
    assert target_part.subtitle_reset_count == 0
