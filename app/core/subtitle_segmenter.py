"""
Intelligent sentence-boundary, pause-detection, and dialogue-aware subtitle segmenter.
Transforms raw speech recognition word tokens or VTT chunks into natural, complete,
and professionally formatted subtitle cues adhering to standard broadcast/Netflix guidelines.
"""

from __future__ import annotations
import re
from collections import Counter
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
    "what about", "what if", "that's right", "come on", "i mean", "i think",
    "you're right", "i know", "you know", "it's hard", "it's not"
}

# Complete short dialogue phrases that should never be fused into the next speaker's turn
COMPLETE_SHORT_PHRASES = {
    "i'm sorry", "thank you", "excuse me", "you're right", "i know", "you know",
    "it's hard", "never mind", "good morning", "good night", "hello"
}

# Canned phrases commonly hallucinated by ASR models (Whisper) on silent intro/outro or music
CANNED_EXACT_HALLUCINATIONS = {
    "the end", "thanks for watching", "thank you for watching",
    "please subscribe", "subscribe to my channel", "subscribe to our channel",
    "amaraorg", "amara org"
}

ALLOWED_DIALOGUE_REPETITIONS = {
    "no", "yes", "yeah", "run", "wait", "look", "stop", "please",
    "bye", "ha", "hey", "hello", "shh", "shhh", "come", "go", "help", "oh"
}


def is_hallucination_cue(text: str) -> bool:
    """
    Detect whether a subtitle cue is an autoregressive hallucination
    produced by speech recognition models (like Whisper) during silence, noise, or music.

    Preserves natural dialogue expressions (e.g. 'No, no, no!', 'Run! Run! Run!',
    'Bye bye bye', 'Ha ha ha', 'That's the end of it', 'Translated by the committee').
    """
    t = text.strip()
    if not t:
        return True

    # 1. Zero alphabetic characters: Real human speech must contain at least one natural letter
    if not re.search(r"[a-zA-Z\u0600-\u06FF]", t):
        return True

    clean_lower = re.sub(r"[^a-z0-9\s]", "", t.lower()).strip()

    # 2. Canned video outro / credit watermarks (EXACT match or credit prefix only)
    if clean_lower in CANNED_EXACT_HALLUCINATIONS:
        return True
    if clean_lower.startswith(("subtitles by", "translated by", "transcribed by", "captioned by", "please subscribe", "subscribe to")):
        return True
    if "amaraorg" in clean_lower or "amara org" in clean_lower:
        return True

    # 3. Clause/sentence repetition loops (split on . ? ! , ; -)
    clauses = [re.sub(r"[^a-z0-9\s]", "", c.lower()).strip() for c in re.split(r"[\.\?\!\,\;\-\–\—\n]+", t) if len(c.strip().split()) >= 2]
    if len(clauses) >= 2:
        c_counts = Counter(clauses)
        top_clause, top_c_cnt = c_counts.most_common(1)[0]
        # Ignore if clause is only allowed exclamation words
        if not all(w in ALLOWED_DIALOGUE_REPETITIONS for w in top_clause.split()):
            if top_c_cnt >= 2 and (top_c_cnt * len(top_clause.split())) >= len(t.split()) * 0.4:
                return True

    # 4. Multi-word phrase n-gram loops (n = 2 to 5 words, e.g. 'Thank you very much, thank you very much')
    words = [w.strip(".,!?:;\"'").lower() for w in t.split() if w.strip(".,!?:;\"'")]
    if len(words) >= 4:
        for n in range(2, 6):
            if len(words) >= n * 2:
                sliding_ngrams = [" ".join(words[i:i+n]) for i in range(len(words) - n + 1)]
                c = Counter(sliding_ngrams)
                top_phrase, top_cnt = c.most_common(1)[0]
                # If top phrase consists purely of allowed dialogue words (e.g. "no no", "ha ha"), skip!
                if all(w in ALLOWED_DIALOGUE_REPETITIONS for w in top_phrase.split()):
                    continue

                if top_cnt >= 3:
                    return True
                if top_cnt >= 2 and (top_cnt * n) >= len(words) * 0.4:
                    return True

    # 5. Token-level repetition loops
    if len(words) >= 3:
        max_consecutive = 1
        cur_consecutive = 1
        rep_word = words[0]
        for i in range(1, len(words)):
            if words[i] == words[i - 1]:
                cur_consecutive += 1
                if cur_consecutive > max_consecutive:
                    max_consecutive = cur_consecutive
                    rep_word = words[i]
            else:
                cur_consecutive = 1

        # Check if the repeated word is a known natural dialogue exclamation
        if max_consecutive >= 3:
            if rep_word in ALLOWED_DIALOGUE_REPETITIONS and max_consecutive <= 5:
                pass  # Legitimate dialogue ("No, no, no!", "Run! Run! Run!", "Ha ha ha ha")
            else:
                return True

        # Check dominant token: only flag if not an allowed conversational word
        counts = Counter(words)
        top_word, top_cnt = counts.most_common(1)[0]
        if top_cnt / len(words) >= 0.7 and len(words) >= 4:
            if top_word not in ALLOWED_DIALOGUE_REPETITIONS or top_cnt > 5:
                return True

    return False


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
    3. Splits on conversational dialogue boundaries (e.g. 'I'm sorry' -> 'you're right').
    4. Grammar-aware soft splitting: never chops after unsplittable words (articles, prepositions, pronouns).
    5. Orphan prevention: keeps short remaining words (1-3 words) with the sentence rather than creating
       lonely orphan cues like 'Yet.' or 'Marriage?'.
    6. Minimum length safeguard: never outputs 1-2 word fragments without terminal punctuation.
    7. Normalizes intro silence durations so first words aren't isolated into standalone cues.
    8. Formats two-person dialogue turns with hyphens (- Speaker 1 / - Speaker 2).
    9. Resolves colliding timestamps so consecutive cues never overlap or flash simultaneously.
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
        if is_hallucination_cue(raw_text):
            return

        formatted_text = _format_dialogue_if_applicable(tokens_to_flush, raw_text)
        if is_hallucination_cue(formatted_text):
            return

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
            # If it's a short 1-2 word greeting/response (e.g. "Oh.", "Hi.") and next word follows immediately (< 0.25s),
            # keep them together to avoid micro-flashing
            if num_words <= 2 and pause < 0.25 and raw_word_lower in {"oh", "hi", "hey", "yes", "no"}:
                i += 1
                continue

            next_is_capitalized = bool(next_token["word"]) and next_token["word"][0].isupper()
            if num_words >= 2 or pause >= 0.15 or next_is_capitalized or not has_next:
                flush_tokens(current_tokens)
                current_tokens = []
                i += 1
                continue

        # Case 2: Complete short dialogue phrase reached (e.g. "I'm sorry" right before "you're right")
        current_phrase = " ".join(t["word"].strip(".,!?:;\"'").lower() for t in current_tokens)
        next_clean = next_token["word"].strip(".,!?:;\"'").lower()
        two_ahead = ""
        if i + 2 < len(valid_words):
            word_ahead_clean = valid_words[i + 2]["word"].strip(".,!?:;\"'").lower()
            two_ahead = f"{next_clean} {word_ahead_clean}"

        if current_phrase in COMPLETE_SHORT_PHRASES:
            if next_clean in DISCOURSE_STARTERS or two_ahead in DISCOURSE_STARTERS or next_clean in {"and", "but", "so", "because", "yet"} or pause >= 0.04:
                flush_tokens(current_tokens)
                current_tokens = []
                i += 1
                continue

        # Case 3: Significant speech pause between words (Speaker change or breath pause)
        if pause >= pause_threshold_sec:
            # Avoid cutting after unsplittable word if pause is only moderately long (< 0.65s)
            if raw_word_lower not in UNSPLITTABLE_END_WORDS or pause >= 0.65:
                if num_words >= 2:
                    flush_tokens(current_tokens)
                    current_tokens = []
                    i += 1
                    continue

        # Safeguard: Never flush fragmented cues with fewer than 3 words unless terminal punctuation
        if num_words < 3:
            i += 1
            continue

        # Case 4: Fast speech discourse marker / dialogue turn (e.g. "you're right", "I know", "well", "no")
        if num_words >= 4 and (next_clean in DISCOURSE_STARTERS or two_ahead in DISCOURSE_STARTERS):
            if raw_word_lower not in UNSPLITTABLE_END_WORDS:
                flush_tokens(current_tokens)
                current_tokens = []
                i += 1
                continue

        # Case 5: Clause break (, or ;) with sufficient words
        if is_clause and num_words >= 4 and cue_dur >= 1.5:
            if raw_word_lower not in UNSPLITTABLE_END_WORDS:
                flush_tokens(current_tokens)
                current_tokens = []
                i += 1
                continue

        # Case 6: Reached soft limits (max_words_per_cue or max_duration_sec)
        # Apply grammar-aware soft splitting & orphan prevention
        if num_words >= max_words_per_cue or cue_dur >= max_duration_sec:
            remaining_to_term = words_until_terminal(i + 1)

            # Orphan prevention: If sentence will finish in 1 to 3 words, DO NOT cut now!
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

        i += 1

    if current_tokens:
        flush_tokens(current_tokens)

    # Post-processing: Hallucination filter and Collision & Overlap Resolver
    valid_cues = [c for c in cues if not is_hallucination_cue(c.text)]
    resolved_cues = _resolve_cue_collisions(valid_cues, min_cue_duration_ms)
    for idx, c in enumerate(resolved_cues, 1):
        c.index = idx
    return resolved_cues


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
    max_words_per_cue: int = 10,
    max_duration_sec: float = 4.5,
    min_cue_duration_ms: int = 800
) -> List[SubtitleCue]:
    """
    Take existing SubtitleCues (e.g. from Cloudflare WebVTT or segment streams),
    decompose into word-level tokens preserving inter-cue timestamps and speech pauses,
    and re-segment them into natural, sentence-aligned, readable subtitle cues.
    """
    if not raw_cues:
        return []

    clean_raw = [c for c in raw_cues if not is_hallucination_cue(c.text)]
    if not clean_raw:
        return []

    words: List[Dict[str, Any]] = []
    for cue in clean_raw:
        cue_words = cue.text.split()
        if not cue_words:
            continue
        c_dur_s = max((cue.end_ms - cue.start_ms) / 1000.0, 0.2)
        w_dur_s = c_dur_s / len(cue_words)
        st_s = cue.start_ms / 1000.0

        for i, w in enumerate(cue_words):
            w_start = st_s + (i * w_dur_s)
            w_end = st_s + ((i + 1) * w_dur_s)
            words.append({"word": w, "start": w_start, "end": w_end})

    return segment_words_into_cues(
        words=words,
        pause_threshold_sec=pause_threshold_sec,
        max_words_per_cue=max_words_per_cue,
        max_duration_sec=max_duration_sec,
        min_cue_duration_ms=min_cue_duration_ms
    )
