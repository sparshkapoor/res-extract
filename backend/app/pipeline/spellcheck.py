"""Deterministic (non-LLM) spelling cleanup for step instructions — catches
residual ASR-garble typos the LLM proofread pass (extract_recipe.proofread_steps)
had no particular reason to flag as suspicious. Runs as a final pass, after
the LLM proofread, in orchestrator.py.

Scoped to Step.instruction only, never ingredient names — too many valid
rare culinary loanwords/proper nouns there for a general dictionary to judge
safely. Conservative by design: only ever applies an edit-distance-1
correction to a word the dictionary (base + culinary_terms) doesn't
recognize at all; anything else is left untouched rather than risk changing
meaning."""

import re

from spellchecker import SpellChecker

from app.models import Step
from app.pipeline.culinary_terms import CULINARY_TERMS

_spell = SpellChecker(distance=1)
_spell.word_frequency.load_words(CULINARY_TERMS)

_WORD_RE = re.compile(r"[A-Za-z']+")
_MIN_WORD_LEN = 4  # shorter words are disproportionately false-positive-prone
# Edit-distance-1 typos frequently collide with a much more common unrelated
# word (e.g. "heet" is distance-1 from "heat" AND "meet" AND "feet" AND 10
# others — plain word-frequency alone confidently, and wrongly, picks "meet").
# Candidate-set size is a cheap, effective ambiguity proxy: a typo genuinely
# close to only 1-3 real words is safe to auto-correct; anything with a wide
# candidate spread is left untouched rather than risk a confident wrong guess.
_MAX_CANDIDATES = 3


def _match_case(original: str, correction: str) -> str:
    if original.isupper():
        return correction.upper()
    if original[:1].isupper():
        return correction[:1].upper() + correction[1:]
    return correction


def _correct_token(word: str) -> str:
    lower = word.lower()
    if len(word) < _MIN_WORD_LEN or lower in _spell:
        return word
    candidates = _spell.candidates(lower)
    if not candidates or len(candidates) > _MAX_CANDIDATES:
        return word
    correction = _spell.correction(lower)
    if correction is None or correction == lower:
        return word
    return _match_case(word, correction)


def clean_text(text: str) -> str:
    return _WORD_RE.sub(lambda m: _correct_token(m.group(0)), text)


def clean_step_text(steps: list[Step]) -> list[Step]:
    for step in steps:
        step.instruction = clean_text(step.instruction)
    return steps
