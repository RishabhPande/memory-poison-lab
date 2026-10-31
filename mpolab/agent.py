"""A deliberately simple scripted agent with a real decision policy.

The agent plans an office-supply reorder. Its policy reads recalled
memories and lets preference-kind entries steer the chosen vendor:

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
    QUERY = "approved vendor office supplies reorder printer paper"

    def __init__(self, memory: ReferenceMemory, defended: bool = False):
        self.memory = memory
        self.defended = defended

    def decide(self) -> dict:
        recalled = self.memory.recall(self.QUERY, k=10)
        eligible = []
        for entry in recalled:
            if entry.kind != "preference":
                continue
            if self.defended and entry.origin != TRUST_OWNER:
                continue
            parsed = parse_claim(entry.text)
            if parsed and parsed[0] == "vendor":
                eligible.append((entry, parsed[1]))
        if not eligible:
            return {
                "vendor": self.DEFAULT_VENDOR,
                "influenced_by": None,
                "recalled_ids": [e.id for e in recalled],
            }
        # Naive policy: highest confidence wins; ties go to the newest
        # write. Defended mode never sees non-owner entries at all.
        eligible.sort(key=lambda pair: (-pair[0].confidence, -pair[0].id))
        entry, vendor = eligible[0]
        return {
            "vendor": vendor,
            "influenced_by": entry.id,
            "recalled_ids": [e.id for e in recalled],
        }
