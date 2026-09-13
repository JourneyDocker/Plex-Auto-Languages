"""
Tests for tie-breaking track selection by stream position.

When several candidate streams tie at the top match score (for example, duplicate
track names), the candidate at the same position within the filtered candidate list
as the reference's selected stream is chosen. When scores are not tied, the score
wins regardless of position.
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
    # Identically named subtitle pair: the reference has the second of the pair
    # selected, so the target must end up with its second selected, not the first.
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
    # Same pair, reference has the first selected: the target's first must be kept.
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


def test_layout_shift_keeps_same_filtered_position():
    # The reference has a forced track the target lacks, so the duplicate pair sits
    # at different raw indices (4/5 in the reference, 3/4 in the target). Position
    # is measured within the filtered list, so the reference's second of the pair
    # maps to the target's second of the pair.
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
    # A genuine score difference (codec) must beat the reference position, even when
    # the reference position points at the weaker candidate.
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


def test_tied_scores_with_reversed_pair_order_use_target_position():
    # With identical names the tie-break is the position within the target's filtered
    # list, so the reference's first-of-pair pick maps to the target's first slot even
    # when the underlying streams are in a different order.
    ref_audio = FakeAudioStream(title="English", selected=True)
    ref_sub_first = FakeSubtitleStream(title="English (PGS)", selected=True)
    ref_sub_second = FakeSubtitleStream(title="English (PGS)")
    reference, _ = make_episode([ref_audio], [ref_sub_first, ref_sub_second])

    tgt_audio = FakeAudioStream(title="English", selected=True)
    tgt_sub_reversed_first = FakeSubtitleStream(title="English (PGS)")
    tgt_sub_reversed_second = FakeSubtitleStream(title="English (PGS)", selected=True)
    target, target_part = make_episode([tgt_audio],
                                       [tgt_sub_reversed_first, tgt_sub_reversed_second])

    track_changes = compute(reference, target)
    assert track_changes.has_changes
    track_changes.apply()
    assert target_part.selected_subtitle_stream is tgt_sub_reversed_first


def test_reference_position_out_of_range_falls_back_to_first():
    # The reference has three duplicates with the third selected; the target has two.
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
    # Reference and target have subtitle streams but none selected: nothing must
    # change and no reset must be issued.
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
