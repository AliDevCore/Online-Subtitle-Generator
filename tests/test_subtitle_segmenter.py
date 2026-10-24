"""
Tests for intelligent subtitle segmentation, sentence boundary splitting,
pause detection, and dialogue formatting.
"""

from app.core.subtitle_segmenter import (
    segment_words_into_cues,
    resegment_cues,
    is_hallucination_cue,
    _format_dialogue_if_applicable,
)
from app.core.types import SubtitleCue


def test_segment_words_sentence_boundaries():
    """Verify that word tokens are split on terminal punctuation."""
    words = [
        {"word": "Hello", "start": 0.0, "end": 0.4},
        {"word": "world.", "start": 0.4, "end": 0.8},
        {"word": "How", "start": 0.9, "end": 1.2},
        {"word": "are", "start": 1.2, "end": 1.4},
        {"word": "you", "start": 1.4, "end": 1.6},
        {"word": "doing?", "start": 1.6, "end": 2.0},
    ]

    cues = segment_words_into_cues(words, pause_threshold_sec=0.40)
    assert len(cues) == 2
    assert cues[0].text == "Hello world."
    assert cues[1].text == "How are you doing?"


def test_segment_words_pause_detection():
    """Verify that speech pauses >= pause_threshold_sec split cues even without punctuation."""
    words = [
        {"word": "Speaker", "start": 1.0, "end": 1.5},
        {"word": "one", "start": 1.5, "end": 1.8},
        # 0.6s silence gap (pause > 0.40s)
        {"word": "Speaker", "start": 2.4, "end": 2.8},
        {"word": "two", "start": 2.8, "end": 3.1},
    ]

    cues = segment_words_into_cues(words, pause_threshold_sec=0.40)
    assert len(cues) == 2
    assert cues[0].text == "Speaker one"
    assert cues[1].text == "Speaker two"


def test_resegment_broken_cues():
    """
    Verify resegment_cues fixes broken line chops where words like 'But'
    were stuck at the end of the previous cue.
    """
    raw_cues = [
        SubtitleCue(1, 0, 5660, "forever and ever. Amen. But"),
        SubtitleCue(2, 5660, 6580, "why is it going to"),
        SubtitleCue(3, 6580, 8080, "be so boring?"),
    ]

    fixed = resegment_cues(raw_cues, pause_threshold_sec=0.40)
    assert len(fixed) >= 2
    # First sentence is complete and not truncated
    assert fixed[0].text == "Forever and ever."
    # "But why is it going to be so boring?" is unified cleanly
    assert any("why is it going to be so boring?" in c.text for c in fixed)


def test_abbreviation_not_split():
    """Verify that abbreviations like Dr. or Mr. do not trigger a split."""
    words = [
        {"word": "Dr.", "start": 0.0, "end": 0.4},
        {"word": "Watson", "start": 0.4, "end": 0.8},
        {"word": "arrived", "start": 0.8, "end": 1.2},
        {"word": "early.", "start": 1.2, "end": 1.6},
    ]
    cues = segment_words_into_cues(words, pause_threshold_sec=0.40)
    assert len(cues) == 1
    assert cues[0].text == "Dr. Watson arrived early."


def test_user_dialogue_resegmentation():
    """Verify that choppy broken cues from user's example are properly reassembled."""
    raw_cues = [
        SubtitleCue(1, 0, 15300, "okay this is the last"),
        SubtitleCue(2, 15300, 16780, "one no go on I"),
        SubtitleCue(3, 16780, 18320, "want to see more it's"),
        SubtitleCue(4, 18320, 20000, "talks are so lame your"),
        SubtitleCue(5, 20000, 23140, "attitude is lame maybe it"),
        SubtitleCue(6, 23140, 24520, "caught sneaking out that one"),
        SubtitleCue(7, 24520, 25240, "of taking her I'm going"),
        SubtitleCue(8, 25240, 25660, "to turn on the phone."),
    ]

    fixed = resegment_cues(raw_cues, pause_threshold_sec=0.40)
    # The broken "last / one" should be together in some cue
    combined_texts = " ".join(c.text for c in fixed)
    assert "last one" in combined_texts.lower()
    assert "i want to see more" in combined_texts.lower()
    assert "phone." in fixed[-1].text.lower()


def test_dialogue_formatting():
    """Test two-speaker turn hyphenation."""
    tokens = [
        {"word": "Shhh.", "start": 0.0, "end": 0.5},
        {"word": "Enough", "start": 0.6, "end": 1.0},
        {"word": "now.", "start": 1.0, "end": 1.4},
        # pause 0.3s
        {"word": "No.", "start": 1.7, "end": 2.0},
        {"word": "Come", "start": 2.1, "end": 2.4},
        {"word": "on.", "start": 2.4, "end": 2.7},
    ]
    formatted = _format_dialogue_if_applicable(tokens, "Shhh. Enough now. No. Come on.")
    assert formatted.startswith("- Shhh. Enough now.")
    assert "- No. Come on." in formatted


def test_orphan_word_prevention():
    """Verify that a sentence ending with 1-2 words is kept intact rather than leaving an orphan word."""
    text = "Not too much trouble because I am not ready to be a grandmother yet."
    words = []
    t = 1.0
    for w in text.split():
        words.append({"word": w, "start": t, "end": t + 0.3})
        t += 0.35

    cues = segment_words_into_cues(words, pause_threshold_sec=0.40)
    # The whole sentence should be kept together, NOT split into "...grandmother" and "Yet."
    assert len(cues) == 1
    assert "grandmother yet." in cues[0].text.lower()


def test_intro_silence_duration_normalization():
    """Verify that Whisper assigning 20s intro silence to word 0 does not isolate word 0."""
    words = [
        {"word": "He's", "start": 0.0, "end": 23.34},
        {"word": "ignoring", "start": 23.34, "end": 23.8},
        {"word": "me.", "start": 23.8, "end": 24.3},
    ]
    cues = segment_words_into_cues(words, pause_threshold_sec=0.40)
    assert len(cues) == 1
    assert cues[0].text == "He's ignoring me."


def test_standalone_short_answers_preserved():
    """Verify that a short dialogue answer like 'Yes.' is preserved as its own cue."""
    words = [
        {"word": "Are", "start": 1.0, "end": 1.2},
        {"word": "you", "start": 1.2, "end": 1.4},
        {"word": "ready?", "start": 1.4, "end": 1.8},
        # pause 0.5s
        {"word": "Yes.", "start": 2.3, "end": 2.7},
        # pause 0.5s
        {"word": "Then", "start": 3.2, "end": 3.5},
        {"word": "let's", "start": 3.5, "end": 3.8},
        {"word": "go.", "start": 3.8, "end": 4.1},
    ]
    cues = segment_words_into_cues(words, pause_threshold_sec=0.40)
    assert len(cues) == 3
    assert cues[0].text == "Are you ready?"
    assert cues[1].text == "Yes."
    assert cues[2].text == "Then let's go."


def test_clustered_timestamps_no_overlap():
    """Verify that Whisper burst timestamps (identical start times) are sequenced without overlap."""
    words = [
        {"word": "Good", "start": 32.4, "end": 32.5},
        {"word": "morning.", "start": 32.5, "end": 32.6},
        # Same start timestamp cluster
        {"word": "What", "start": 32.4, "end": 32.5},
        {"word": "are", "start": 32.5, "end": 32.6},
        {"word": "you", "start": 32.6, "end": 32.7},
        {"word": "doing?", "start": 32.7, "end": 32.8},
    ]
    cues = segment_words_into_cues(words, pause_threshold_sec=0.40)
    assert len(cues) == 2
    assert cues[0].text == "Good morning."
    assert cues[1].text == "What are you doing?"
    # Must NOT overlap!
    assert cues[1].start_ms >= cues[0].end_ms


def test_is_hallucination_cue_filters_zero_letter_and_loops():
    """Verify that is_hallucination_cue catches Whisper artifacts on silence/intro."""
    # Zero letters / digits / symbols
    assert is_hallucination_cue("4") is True
    assert is_hallucination_cue("-5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5") is True
    assert is_hallucination_cue("-4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -") is True
    assert is_hallucination_cue("...") is True
    assert is_hallucination_cue("--") is True

    # Repetition loops (both periods and commas/n-grams)
    assert is_hallucination_cue("you you you you") is True
    assert is_hallucination_cue("Thank you very much. Thank you very much. Thank you very much.") is True
    assert is_hallucination_cue("Thank you very much, thank you very much, thank you very much, thank you very much,") is True
    assert is_hallucination_cue("Thank you very much, thank you very much, thank you very") is True

    # Canned video watermarks
    assert is_hallucination_cue("Thanks for watching!") is True
    assert is_hallucination_cue("Please subscribe to my channel.") is True
    assert is_hallucination_cue("Subtitles by the Amara.org community") is True

    # Legitimate dialogue MUST NOT be filtered
    assert is_hallucination_cue("Hey, were you out there?") is False
    assert is_hallucination_cue("Yeah, I was.") is False
    assert is_hallucination_cue("Checking on my flowers.") is False
    assert is_hallucination_cue("Thank you.") is False
    assert is_hallucination_cue("Yes.") is False
    assert is_hallucination_cue("Room 404") is False
    assert is_hallucination_cue("Call 911 immediately!") is False
    assert is_hallucination_cue("That's the end of it.") is False
    assert is_hallucination_cue("No, no, no, no!") is False
    assert is_hallucination_cue("Run! Run! Run!") is False
    assert is_hallucination_cue("Ha ha ha ha") is False
    assert is_hallucination_cue("Bye bye bye.") is False
    assert is_hallucination_cue("He was translated by the committee.") is False
    assert is_hallucination_cue("At the end of the day, we won.") is False


def test_resegment_cues_eliminates_user_reported_silence_hallucinations():
    """Simulate user's exact issue where cues 1-17 are noise numbers and cues 18-20 are dialogue."""
    raw_cues = [
        SubtitleCue(1, 0, 800, "4"),
        SubtitleCue(2, 5620, 6420, "-5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5"),
        SubtitleCue(3, 6460, 7260, "-5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5"),
        SubtitleCue(4, 9220, 11620, "-5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5"),
        SubtitleCue(5, 13800, 14600, "-5 -5 -5 -5 -5 -5 -5"),
        SubtitleCue(6, 17340, 21660, "-5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5"),
        SubtitleCue(7, 21660, 22460, "-5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5"),
        SubtitleCue(8, 22500, 23300, "-5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5 -5"),
        SubtitleCue(9, 40960, 42600, "-4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4"),
        SubtitleCue(10, 42640, 45200, "-4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4"),
        SubtitleCue(11, 45200, 46280, "-4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4"),
        SubtitleCue(12, 60580, 62220, "-4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4"),
        SubtitleCue(13, 62260, 63900, "-4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4"),
        SubtitleCue(14, 63940, 65580, "-4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4"),
        SubtitleCue(15, 65620, 67260, "-4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4"),
        SubtitleCue(16, 67300, 68940, "-4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4"),
        SubtitleCue(17, 68980, 69780, "-4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -4 -"),
        SubtitleCue(18, 87120, 88700, "Hey, were you out there?"),
        SubtitleCue(19, 89000, 89980, "Yeah, I was."),
        SubtitleCue(20, 90900, 92800, "Checking on my flowers.")
    ]

    filtered_cues = resegment_cues(raw_cues)
    # Exactly the 3 dialogue cues should remain!
    assert len(filtered_cues) == 3
    assert filtered_cues[0].text == "Hey, were you out there?"
    assert filtered_cues[1].text == "Yeah, I was."
    assert filtered_cues[2].text == "Checking on my flowers."
    # Re-indexed starting from 1
    assert filtered_cues[0].index == 1
    assert filtered_cues[1].index == 2
    assert filtered_cues[2].index == 3

