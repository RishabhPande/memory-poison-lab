"""Shared policy helpers: claim parsing, compaction planning and
conflict-scoped repair, used identically by every memory backend.

Repair is deliberately *conflict-scoped*, not general: it removes
quarantined writes and non-owner preference entries that contradict
the owner's newest parseable policy claim on the same subject. It
cannot detect conflicts it cannot parse - that limit is documented
and covered by tests, not hidden.
"""

from __future__ import annotations

import re
from typing import Optional

_CLAIM_PATTERNS = [
    ("vendor", re.compile(
        r"approved vendor(?:\s+is)?(?:\s+now)?\s*:?\s*([A-Za-z0-9][A-Za-z0-9.\-]*)",
        re.IGNORECASE)),
    ("courier", re.compile(
        r"preferred courier(?:\s+is)?(?:\s+now)?\s*:?\s*([A-Za-z0-9][A-Za-z0-9.\-]*)",
        re.IGNORECASE)),
]

_PREFERENCE_SIGNALS = (
    "approved vendor",
    "preferred vendor",
    "preferred courier",
    "from now on",
    "always order",
    "user prefers",
)


def parse_claim(text: str) -> Optional[tuple[str, str]]:
    """Extract a (subject, value) policy claim, or None.

    Only the claim shapes above are parseable. A poisoning write that
    never parses cannot steer the scripted agent either - the range
    treats that as a coverage fact, not a defense.
    """
    for subject, pattern in _CLAIM_PATTERNS:
        match = pattern.search(text)
        if match:
            return subject, match.group(1).rstrip(".")
    return None


def preference_sentences(text: str) -> list[str]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    return [s for s in sentences if any(sig in s.lower() for sig in _PREFERENCE_SIGNALS)]


def owner_claims(entries) -> dict[str, tuple[str, int]]:
    """The owner's newest parseable claim per subject: subject -> (value, step)."""
    claims: dict[str, tuple[str, int]] = {}
    for entry in entries:
        if entry.origin != "owner":
            continue
        parsed = parse_claim(entry.text)
        if not parsed:
            continue
        subject, value = parsed
        if subject not in claims or entry.step >= claims[subject][1]:
            claims[subject] = (value, entry.step)
    return claims


def compact_plan(entries, step: int, start_id: int) -> tuple[list[dict], list[int]]:
    """Decide what extractive compaction keeps.

    Owner-origin entries are never compacted. For every other entry,
    sentences carrying a preference signal survive as a new summary
    entry whose trust LABEL becomes 'summary' while its origin keeps
    the true provenance. Returns (summary_specs, drop_ids).
    """
    summaries: list[dict] = []
    drop: list[int] = []
    next_id = start_id
    for entry in entries:
        if entry.origin == "owner":
            continue
        drop.append(entry.id)
        surviving = preference_sentences(entry.text)
        if surviving:
            summaries.append({
                "id": next_id,
                "text": " ".join(surviving),
                "trust": "summary",
                "origin": entry.origin,
                "kind": "preference",
                "step": step,
                "confidence": entry.confidence,
                "source": f"compacted from entry {entry.id}",
            })
            next_id += 1
    return summaries, drop


def repair_plan(entries) -> list[int]:
    """Conflict-scoped repair: which entry ids to remove.

    Removes (a) quarantined writes and (b) non-owner preference
    entries whose parseable claim contradicts the owner's newest
    claim on the same subject. Everything else - benign untrusted
    facts, non-conflicting non-owner preferences - is kept.
    """
    claims = owner_claims(entries)
    removed: list[int] = []
    for entry in entries:
        if entry.quarantined:
            removed.append(entry.id)
            continue
        if entry.origin == "owner" or entry.kind != "preference":
            continue
        parsed = parse_claim(entry.text)
        if not parsed:
            continue
        subject, value = parsed
        if subject in claims and claims[subject][0].lower() != value.lower():
            removed.append(entry.id)
    return removed
