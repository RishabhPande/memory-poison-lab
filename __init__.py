"""mpo-lab: an agent memory poisoning test range.

Synthetic targets only. The bundled scripted agent demonstrates the
mechanics of memory poisoning; it is not evidence about the safety of
any real LLM.
"""

from .memory import MemoryEntry, ReferenceMemory, TRUST_OWNER, TRUST_TOOL, TRUST_SUMMARY
from .agent import ScriptedSupplyAgent
from .scenarios import SCENARIOS, run_scenario, run_all

__all__ = [
    "MemoryEntry",
    "ReferenceMemory",
    "TRUST_OWNER",
    "TRUST_TOOL",
    "TRUST_SUMMARY",
    "ScriptedSupplyAgent",
    "SCENARIOS",
    "run_scenario",
    "run_all",
]
