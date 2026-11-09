"""Step 3: Answer drafting with strict evidence grounding and inline citations.

Formats retrieved passage excerpts into structured context prompts and parses
bracketed inline citations matching the required [Paper, Section, Page] format.
"""

from __future__ import annotations

import re

from passageworks.models import Citation, PassageChunk

DRAFT_SYSTEM_PROMPT: str = """You are Passageworks, a precise, paper-grounded technical research assistant.
You answer engineering questions strictly and solely using the provided paper excerpts.

CITATION RULES:
1. Every claim, number, formula, or finding must have an immediate citation tag.
2. Citation format must be exactly: [Paper Title, Section Title, p.X]
   For example: [Attention Is All You Need, 3.2 Scaled Dot-Product Attention, p.4]
3. If the provided excerpts do not contain the answer, you MUST state:
   "The provided excerpts do not contain sufficient evidence to answer this question."
4. Never assume, extrapolate, or bring in knowledge from other papers or general knowledge.
"""


def format_evidence_context(chunks: list[PassageChunk]) -> str:
    """Format a list of retrieved passages into a structured markdown prompt block.

    Args:
        chunks: List of retrieved PassageChunk instances.

    Returns:
        Structured string block presenting excerpts with paper, section, and page metadata.
    """
    context_blocks = []
    for i, c in enumerate(chunks, 1):
        block = (
            f"--- EXCERPT {i} ---\n"
            f"Paper: {c.paper_title} ({c.arxiv_id})\n"
            f"Section: {c.section_title}\n"
            f"Page: {c.page_number}\n"
            f"Chunk ID: {c.chunk_id}\n\n"
            f"{c.text}\n"
        )
        context_blocks.append(block)
    return "\n".join(context_blocks)


def extract_citations(text: str) -> list[Citation]:
    """Extract structured citation tags from draft text matching [Paper, Section, p.X].

    Args:
        text: Synthesized answer string containing bracketed citations.

    Returns:
        List of parsed Citation dataclass instances.
    """
    citations = []
    # Pattern: [Paper Name, Section Name, p.12]
    pattern = re.compile(
        r"\[([A-Za-z0-9\s,\-:]{3,60}),\s*([A-Za-z0-9\s,\-:\.]{1,60}),\s*p\.?(\d+)\]"
    )
    for m in pattern.finditer(text):
        raw = m.group(0)
        paper = m.group(1).strip()
        section = m.group(2).strip()
        page = int(m.group(3))
        citations.append(
            Citation(
                paper_title=paper,
                arxiv_id="",
                section=section,
                page=page,
                raw_citation=raw,
            )
        )
    return citations
