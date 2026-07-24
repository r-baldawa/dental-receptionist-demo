"""
Clinic knowledge loader — reads atlas_dental_clinic_knowledge.md directly into context.
No retrieval pipeline; Phase 5 wires this into node prompts.
See plan.md §6: vector DB / embeddings is out of scope for this build.
"""
from pathlib import Path

_KB_PATH = Path(__file__).parent.parent.parent / "atlas_dental_clinic_knowledge.md"
_content: str | None = None


def get_clinic_knowledge() -> str:
    """Return the full clinic knowledge doc as a string (cached on first read)."""
    global _content
    if _content is None:
        with open(_KB_PATH, encoding="utf-8") as f:
            _content = f.read()
    return _content
