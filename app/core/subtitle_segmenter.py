"""
Intelligent sentence-boundary, pause-detection, and dialogue-aware subtitle segmenter.
Transforms raw speech recognition word tokens or VTT chunks into natural, complete,
and professionally formatted subtitle cues adhering to standard broadcast/Netflix guidelines.
"""

from __future__ import annotations
import re
from typing import List, Dict, Any, Optional
from app.core.types import SubtitleCue

TERMINAL_PUNCTUATION = {".", "?", "!", "...", '."', '?"', '!"'}
CLAUSE_PUNCTUATION = {",", ";", ":", "--", "-"}
ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "st.", "vs.", "etc.",
    "e.g.", "i.e.", "jr.", "sr.", "co.", "ltd.", "inc."
}

# Words that should NEVER appear at the very end of a subtitle cue (unless ended with terminal punctuation)
UNSPLITTABLE_END_WORDS = {
    # Articles & determiners
    "a", "an", "the", "my", "your", "his", "her", "its", "our", "their",
    "this", "that", "these", "those",
    # Prepositions
    "of", "in", "to", "for", "with", "on", "at", "from", "by", "about", "as",
    "into", "like", "through", "after", "over", "between", "out", "against",
    "during", "without", "before", "under", "around", "among", "upon", "onto",
    # Pronouns & subject contractions
    "i", "i'm", "you", "you're", "he", "he's", "she", "she's", "it", "it's",
    "we", "we're", "they", "they're", "who", "what", "which",
    # Conjunctions
    "and", "but", "or", "nor", "so", "yet", "because", "if", "than", "whether",
    # Auxiliary verbs & modals
    "is", "am", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did",
    "will", "would", "shall", "should", "can", "could", "may", "might", "must",
    # Adverbs / intensifiers that lead into something
    "too", "very", "more", "most", "just"
}

# Discourse / conversational sentence starters for unpunctuated speech
DISCOURSE_STARTERS = {
    "no", "yes", "yeah", "okay", "well", "look", "listen", "wait",
    "what about", "what if", "that's right", "come on", "i mean", "i think"
}


def _is_terminal(word: str) -> bool:
    """Check if word ends with terminal punctuation and is not an abbreviation."""
    w = word.strip().rstrip('"\'')
    if w.lower() in ABBREVIATIONS:
        return False
    return any(w.endswith(p) for p in TERMINAL_PUNCTUATION)


def _is_clause_break(word: str) -> bool:
    """Check if word ends with clause-level punctuation."""
    w = word.strip().rstrip('"\'')
    return any(w.endswith(p) for p in CLAUSE_PUNCTUATION)


def _clean_cue_text(text: str) -> str:
    """Clean and capitalize the subtitle text."""
    t = text.strip()
    if not t:
        return ""
    if t[0].islower():
        t = t[0].upper() + t[1:]
    return t


def _normalize_word_token(token: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize word token and clamp abnormally long durations caused by intro silence."""
    st = float(token.get("start", 0.0))
    end = float(token.get("end", st + 0.2))
    txt = str(token.get("word", "")).strip()

    # If Whisper attributed tens of seconds of intro silence to a single word,
    # clamp start time to right before end time so it stays with the sentence.
    if end - st > 2.0:
        st = max(0.0, end - 0.6)

    return {"word": txt, "start": st, "end": end}


def segment_words_into_cues(
    words: List[Dict[str, Any]],
    pause_threshold_sec: float = 0.40,
    max_words_per_cue: int = 14,
    max_duration_sec: float = 6.0,
    min_cue_duration_ms: int = 800
) -> List[SubtitleCue]:
    """
    Segment word-level timestamps into natural, sentence-aligned subtitle cues.
    
    Features:
    1. Splits on terminal punctuation (., ?, !).
    2. Splits on speech pauses / silence between words (>= pause_threshold_sec).
    3. Grammar-aware soft splitting: never chops after unsplittable words (articles, prepositions, pronouns).
    4. Orphan prevention: keeps short remaining words (1-3 words) with the sentence rather than creating
       lonely orphan cues like 'Yet.' or 'Marriage?'.
    5. Normalizes intro silence durations so first words aren't isolated into standalone cues.
    6. Formats two-person dialogue turns with hyphens (- Speaker 1 / - Speaker 2).
    7. Resolves colliding timestamps so consecutive cues never overlap or flash simultaneously.
    """
    if not words:
        return []

    # Clean, filter, and normalize word tokens
    valid_words: List[Dict[str, Any]] = []
    for w in words:
        txt = str(w.get("word", "")).strip()
        if not txt:
            continue
        try:
            norm = _normalize_word_token(w)
            if norm["end"] >= norm["start"]:
                valid_words.append(norm)
        except (ValueError, TypeError):
            continue

    if not valid_words:
        return []

    cues: List[SubtitleCue] = []
    current_tokens: List[Dict[str, Any]] = []

    def flush_tokens(tokens_to_flush: List[Dict[str, Any]]):
        if not tokens_to_flush:
            return

        st_ms = int(tokens_to_flush[0]["start"] * 1000)
        end_ms = int(tokens_to_flush[-1]["end"] * 1000)

        # Minimum duration
        if end_ms - st_ms < min_cue_duration_ms:
            end_ms = st_ms + min_cue_duration_ms

        words_text = [t["word"] for t in tokens_to_flush]
        raw_text = " ".join(words_text).strip()
        formatted_text = _format_dialogue_if_applicable(tokens_to_flush, raw_text)

        cues.append(SubtitleCue(
            index=len(cues) + 1,
            start_ms=st_ms,
            end_ms=end_ms,
            text=formatted_text
        ))

    def words_until_terminal(start_idx: int) -> int:
        """Count words until the next terminal punctuation or major pause."""
        count = 0
        for k in range(start_idx, len(valid_words)):
            count += 1
            if _is_terminal(valid_words[k]["word"]):
                return count
            if k + 1 < len(valid_words):
                if valid_words[k + 1]["start"] - valid_words[k]["end"] >= pause_threshold_sec:
                    return count
            if count >= 8:
                break
        return count

    i = 0
    while i < len(valid_words):
        token = valid_words[i]
        current_tokens.append(token)
        has_next = (i + 1 < len(valid_words))

        if not has_next:
            flush_tokens(current_tokens)
            current_tokens = []
            break

        next_token = valid_words[i + 1]
        pause = next_token["start"] - token["end"]
        is_term = _is_terminal(token["word"])
        is_clause = _is_clause_break(token["word"])
        raw_word_lower = token["word"].strip(".,!?:;\"'").lower()

        cue_dur = token["end"] - current_tokens[0]["start"]
        num_words = len(current_tokens)

        # Case 1: Terminal punctuation reached (., ?, !)
        if is_term:
            # Standalone answers like "Yes.", "No.", "Why?" are valid and should flush
            # But avoid flushing if it's literally word 0 and next word follows with 0 pause
            next_is_capitalized = bool(next_token["word"]) and next_token["word"][0].isupper()
            if num_words >= 2 or pause >= 0.15 or next_is_capitalized or not has_next:
                flush_tokens(current_tokens)
                current_tokens = []
                i += 1
                continue

        # Case 2: Significant speech pause between words (Speaker change or breath pause)
        if pause >= pause_threshold_sec:
            # Avoid cutting after unsplittable word if pause is only moderately long (< 0.65s)
            if raw_word_lower not in UNSPLITTABLE_END_WORDS or pause >= 0.65:
                flush_tokens(current_tokens)
                current_tokens = []
                i += 1
                continue

        # Case 3: Reached soft limits (max_words_per_cue or max_duration_sec)
        # Apply grammar-aware soft splitting & orphan prevention
        if num_words >= max_words_per_cue or cue_dur >= max_duration_sec:
            remaining_to_term = words_until_terminal(i + 1)

            # Orphan prevention: If sentence will finish in 1 to 3 words, DO NOT cut now!
            # Let the cue absorb those 1-3 words and finish cleanly together.
            if remaining_to_term <= 3 and num_words <= (max_words_per_cue + 3) and cue_dur < (max_duration_sec + 2.0):
                i += 1
                continue

            # Grammar check: Never cut right after an unsplittable word (article, preposition, pronoun)
            if raw_word_lower in UNSPLITTABLE_END_WORDS:
                i += 1
                continue

            # Balanced split: If we have a good break point or clause, flush
            flush_tokens(current_tokens)
            current_tokens = []
            i += 1
            continue

        # Case 4: Clause break (, or ;) with sufficient words
        if is_clause and num_words >= 6 and cue_dur >= 2.5:
            if raw_word_lower not in UNSPLITTABLE_END_WORDS:
                flush_tokens(current_tokens)
                current_tokens = []
                i += 1
                continue

        # Case 5: Fast speech discourse marker (e.g. "What about", "That's right", "No")
        # If running on for 6+ words without punctuation and encountering a conversational boundary
        if num_words >= 6:
            next_word_lower = next_token["word"].strip(".,!?:;\"'").lower()
            if next_word_lower in DISCOURSE_STARTERS and pause >= 0.10:
                if raw_word_lower not in UNSPLITTABLE_END_WORDS:
                    flush_tokens(current_tokens)
                    current_tokens = []
                    i += 1
                    continue

        i += 1

    if current_tokens:
        flush_tokens(current_tokens)

    # Post-processing: Collision & Overlap Resolver
    cues = _resolve_cue_collisions(cues, min_cue_duration_ms)
    return cues


def _resolve_cue_collisions(cues: List[SubtitleCue], min_duration_ms: int = 800) -> List[SubtitleCue]:
    """
    Ensure cues have strictly monotonically increasing timestamps and never collide
    or overlap on top of each other.
    """
    if not cues:
        return []

    resolved: List[SubtitleCue] = []
    for idx, cue in enumerate(cues, 1):
        c = SubtitleCue(
            index=idx,
            start_ms=cue.start_ms,
            end_ms=max(cue.end_ms, cue.start_ms + min_duration_ms),
            text=cue.text
        )

        if not resolved:
            resolved.append(c)
            continue

        prev = resolved[-1]

        # Check collision with previous cue
        if c.start_ms < prev.end_ms:
            # If start times are identical or within 400ms (Whisper burst cluster)
            # Chain them sequentially so they don't overlap!
            if abs(c.start_ms - prev.start_ms) < 400:
                c.start_ms = prev.end_ms + 40
                c.end_ms = max(c.end_ms, c.start_ms + min_duration_ms)
            else:
                # Moderate overlap: clamp start or previous end
                overlap = prev.end_ms - c.start_ms
                if overlap > 0:
                    midpoint = (prev.end_ms + c.start_ms) // 2
                    if midpoint - prev.start_ms >= min_duration_ms:
                        prev.end_ms = midpoint
                        c.start_ms = midpoint + 40
                    else:
                        c.start_ms = prev.end_ms + 40
                    c.end_ms = max(c.end_ms, c.start_ms + min_duration_ms)

        resolved.append(c)

    return resolved


def _format_dialogue_if_applicable(tokens: List[Dict[str, Any]], full_text: str) -> str:
    """
    Format two-speaker dialogue turns within a single cue using standard hyphens.
    Example:
    "- Shhh. Enough now.\n- No. Come on."
    """
    if len(tokens) < 4:
        return _clean_cue_text(full_text)

    # Look for an internal sentence boundary followed by a pause (>= 0.25s) or question mark
    split_idx = -1
    for i in range(1, len(tokens) - 1):
        prev_tok = tokens[i]
        next_tok = tokens[i + 1]
        pause = next_tok["start"] - prev_tok["end"]
        if _is_terminal(prev_tok["word"]) and (pause >= 0.25 or prev_tok["word"].endswith("?")):
            split_idx = i + 1
            break

    if split_idx != -1:
        part1 = " ".join(t["word"] for t in tokens[:split_idx]).strip()
        part2 = " ".join(t["word"] for t in tokens[split_idx:]).strip()
        if len(part1.split()) >= 1 and len(part2.split()) >= 1:
            return f"- {_clean_cue_text(part1)}\n- {_clean_cue_text(part2)}"

    return _clean_cue_text(full_text)


def resegment_cues(
    raw_cues: List[SubtitleCue],
    pause_threshold_sec: float = 0.40,
    max_words_per_cue: int = 14,
    max_duration_sec: float = 6.0
) -> List[SubtitleCue]:
    """
    Take existing SubtitleCues with broken line splits, interpolate word timestamps,
    and re-segment them into natural sentence-aligned cues.
    """
    if not raw_cues:
        return []

    words: List[Dict[str, Any]] = []
    for cue in raw_cues:
        cue_words = cue.text.split()
        if not cue_words:
            continue
        c_dur_ms = max(cue.end_ms - cue.start_ms, 500)
        w_dur_s = (c_dur_ms / 1000.0) / len(cue_words)
        st_s = cue.start_ms / 1000.0

        for i, w in enumerate(cue_words):
            w_start = st_s + (i * w_dur_s)
            w_end = w_start + w_dur_s
            words.append({"word": w, "start": w_start, "end": w_end})

    return segment_words_into_cues(
        words=words,
        pause_threshold_sec=pause_threshold_sec,
        max_words_per_cue=max_words_per_cue,
        max_duration_sec=max_duration_sec
    )
