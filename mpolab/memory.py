"""A local, deterministic agent-memory backend.

Implements the retain/recall contract used by hosted agent-memory
layers (the "name the verbs" API shape: retain a write, recall by
query). Every entry carries two provenance fields:

- trust:  the storage class the backend reports ("owner", "summary",
          "tool_untrusted"). Compaction can relabel an entry's trust
          without changing where the content actually came from.
- origin: the true provenance, recorded at write time and never
          rewritten. Defenses reason about origin, not the label.

The class is deliberately small and stdlib-only so the whole test
range runs anywhere Python runs. It is a real, working memory store -
the attack and defense mechanics below operate on its actual
retrieval behaviour, not on a mock.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .policy import compact_plan, repair_plan

TRUST_OWNER = "owner"
TRUST_TOOL = "tool_untrusted"
TRUST_SUMMARY = "summary"

_WORD = re.compile(r"[a-z0-9]+")

# Phrases that make a memory look like a standing preference rather
# than an episode. Used by the (deliberately naive) write-time
# classifier.
PREFERENCE_SIGNALS = (
    "approved vendor",
    "preferred vendor",
    "from now on",
    "always order",
    "user prefers",
)

# Instruction-shaped content inside untrusted tool output. The
# write-time screener quarantines matches instead of letting them
# into the recallable store.
INSTRUCTION_LIKE = re.compile(
    r"(approved vendor is now|from now on|ignore (all|any|previous)|"
    r"always order|do not use|route all)",
    re.IGNORECASE,
)


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _norm(text: str) -> str:
    return " ".join(_tokens(text))


def classify(text: str) -> str:
    lowered = text.lower()
    return "preference" if any(s in lowered for s in PREFERENCE_SIGNALS) else "episodic"


@dataclass
class MemoryEntry:
    id: int
    text: str
    trust: str
    origin: str
    kind: str
    step: int
    confidence: float = 1.0
    quarantined: bool = False
    source: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "trust": self.trust,
            "origin": self.origin,
            "kind": self.kind,
            "step": self.step,
            "confidence": round(self.confidence, 3),
            "quarantined": self.quarantined,
            "source": self.source,
        }


class ReferenceMemory:
    """Deterministic local memory: lexical retrieval, repetition
    merging, optional write-time screening, extractive compaction."""

    def __init__(self, screen_writes: bool = False):
        self.screen_writes = screen_writes
        self._entries: list[MemoryEntry] = []
        self._next_id = 1

    def retain(self, text: str, trust: str, step: int, source: str = "") -> MemoryEntry:
        norm = _norm(text)
        for existing in self._entries:
            if _norm(existing.text) == norm:
                # Repetition: an identical claim raises confidence,
                # whatever its provenance. Attack class A3 lives here.
                existing.confidence += 0.5
                return existing
        quarantined = bool(
            self.screen_writes and trust == TRUST_TOOL and INSTRUCTION_LIKE.search(text)
        )
        entry = MemoryEntry(
            id=self._next_id,
            text=text,
            trust=trust,
            origin=trust,
            kind=classify(text),
            step=step,
            confidence=1.0,
            quarantined=quarantined,
            source=source,
        )
        self._next_id += 1
        self._entries.append(entry)
        return entry

    def recall(self, query: str, k: int = 5, include_quarantined: bool = False) -> list[MemoryEntry]:
        qset = set(_tokens(query))
        scored: list[tuple[float, MemoryEntry]] = []
        for entry in self._entries:
            if entry.quarantined and not include_quarantined:
                continue
            etoks = _tokens(entry.text)
            if not etoks:
                continue
            overlap = len(qset & set(etoks))
            if overlap == 0:
                continue
            score = overlap / math.sqrt(len(etoks)) + 0.05 * entry.confidence
            scored.append((score, entry))
        scored.sort(key=lambda item: (-item[0], item[1].id))
        return [entry for _, entry in scored[:k]]

    def compact(self, step: int) -> list[MemoryEntry]:
        """Summarize non-owner entries into trust='summary' entries.

        Extractive and deterministic: sentences carrying a preference
        signal survive. The summary's *label* becomes 'summary' while
        its *origin* keeps the true provenance - the laundering gap.
        """
        summaries, drop = compact_plan(self._entries, step, self._next_id)
        drop_set = set(drop)
        self._entries = [e for e in self._entries if e.id not in drop_set]
        produced = []
        for spec in summaries:
            entry = MemoryEntry(quarantined=False, **spec)
            produced.append(entry)
            self._entries.append(entry)
            self._next_id = max(self._next_id, entry.id + 1)
        return produced

    def entries(self, include_quarantined: bool = True) -> list[MemoryEntry]:
        if include_quarantined:
            return list(self._entries)
        return [e for e in self._entries if not e.quarantined]

    def delete(self, entry_id: int) -> bool:
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.id != entry_id]
        return len(self._entries) != before

    def repair(self) -> list[int]:
        """Conflict-scoped repair (see policy.repair_plan): removes
        quarantined writes and non-owner preferences contradicting the
        owner's newest claim. Returns removed ids."""
        removed = repair_plan(self._entries)
        removed_set = set(removed)
        self._entries = [e for e in self._entries if e.id not in removed_set]
        return removed
