"""A deliberately simple scripted agent with a real decision policy.

The agent plans an office-supply reorder. Its policy reads recalled
memories and lets preference-kind entries steer two decisions:

- vendor:  who to order office supplies from
- courier: who delivers them

Two decision modes:

- naive mode: the preference with the highest (confidence, recency)
  wins, whatever its provenance. This is the failure mode under test:
  retained content steers action.
- defended mode: only entries whose true *origin* is the owner may
  steer. Trust labels assigned later (e.g. by compaction) do not
  count.

The agent is scripted and deterministic. It demonstrates the
mechanics of memory poisoning and repair; it is not evidence about
the behaviour of any real LLM.
"""

from __future__ import annotations

from .memory import ReferenceMemory, TRUST_OWNER
from .policy import parse_claim


class ScriptedSupplyAgent:
    DEFAULT_VENDOR = "OfficeDepot"
    DEFAULT_COURIER = "StandardShip"
    QUERY = "approved vendor office supplies reorder printer paper"
    COURIER_QUERY = "preferred courier shipping delivery office supplies"

    # subject -> (fallback decision, recall query)
    SUBJECTS = {
        "vendor": (DEFAULT_VENDOR, QUERY),
        "courier": (DEFAULT_COURIER, COURIER_QUERY),
    }

    def __init__(self, memory: ReferenceMemory, defended: bool = False):
        self.memory = memory
        self.defended = defended

    def decide(self, subject: str = "vendor") -> dict:
        default, query = self.SUBJECTS[subject]
        recalled = self.memory.recall(query, k=10)
        eligible = []
        for entry in recalled:
            if entry.kind != "preference":
                continue
            if self.defended and entry.origin != TRUST_OWNER:
                continue
            parsed = parse_claim(entry.text)
            if parsed and parsed[0] == subject:
                eligible.append((entry, parsed[1]))
        if not eligible:
            return {
                subject: default,
                "influenced_by": None,
                "recalled_ids": [e.id for e in recalled],
            }
        # Naive policy: highest confidence wins; ties go to the newest
        # write. Defended mode never sees non-owner entries at all.
        eligible.sort(key=lambda pair: (-pair[0].confidence, -pair[0].id))
        entry, value = eligible[0]
        return {
            subject: value,
            "influenced_by": entry.id,
            "recalled_ids": [e.id for e in recalled],
        }
