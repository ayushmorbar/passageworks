"""Step 4: Answer verification and bounded revision control for Passageworks.

Audits candidate draft answers against retrieved evidence excerpts, ensuring citation
presence, factual support, and zero hallucinations before releasing output to users.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from passageworks.models import Citation

VERIFIER_PROMPT: str = """You are the Fact Verification Auditor for Passageworks.
Your job is to strictly verify whether the drafted answer is 100% supported by the retrieved paper excerpts.

INPUTS:
1. Retrieved Evidence Excerpts
2. Drafted Answer

EVALUATION CRITERIA:
1. Citation Presence: Does every factual assertion cite an excerpt?
2. Citation Faithfulness: Does the cited excerpt actually state what the answer claims?
3. Hallucination Check: Does the answer introduce any external facts, assumptions, or extrapolation?

Respond in strict JSON with keys:
- "is_valid": true | false
- "unsupported_claims": [list of strings describing specific claims that lack evidence]
- "suggested_revisions": string guidance for drafting correction
"""


@dataclass
class VerificationOutcome:
    """Diagnostic outcome of the verification evaluation stage.

    Attributes:
        is_valid: True if answer has valid citations and is 100% supported by evidence.
        unsupported_claims: List of specific claims flagged as unsupported or ungrounded.
        suggested_revision: Actionable feedback guiding the re-drafting loop.
        has_valid_citations: Boolean indicating whether citation syntax passed verification.
    """

    is_valid: bool
    unsupported_claims: list[str]
    suggested_revision: str
    has_valid_citations: bool


def verify_citation_syntax(citations: list[Citation]) -> bool:
    """Verify that citations exist and satisfy structural and page boundary checks.

    Args:
        citations: List of parsed Citation instances.

    Returns:
        True if at least one citation exists and all citations have plausible metadata.
    """
    if not citations:
        return False
    for c in citations:
        if c.page < 1 or c.page > 100:
            return False
        if not c.paper_title or not c.section:
            return False
    return True


def parse_verification_response(raw_text: str, citations: list[Citation]) -> VerificationOutcome:
    """Parse and validate JSON evaluation emitted by the verifier model.

    Args:
        raw_text: Raw JSON string from the verification LLM.
        citations: Extracted citations from the candidate draft.

    Returns:
        VerificationOutcome detailing validity and detected discrepancies.
    """
    has_citations = verify_citation_syntax(citations)
    try:
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        data = json.loads(cleaned)
        is_valid = bool(data.get("is_valid", False)) and has_citations
        unsupported = list(data.get("unsupported_claims", []))
        revision = str(data.get("suggested_revisions", ""))

        return VerificationOutcome(
            is_valid=is_valid,
            unsupported_claims=unsupported,
            suggested_revision=revision,
            has_valid_citations=has_citations,
        )
    except Exception as exc:
        return VerificationOutcome(
            is_valid=False,
            unsupported_claims=[f"Verification parse error: {exc}"],
            suggested_revision="Regenerate answer with strict adherence to cited excerpts.",
            has_valid_citations=has_citations,
        )
