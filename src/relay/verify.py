"""Step 4: Answer verification and bounded revision control."""

import json
from dataclasses import dataclass
from typing import List

from relay.models import Citation


VERIFIER_PROMPT = """You are the Fact Verification Auditor for Passageworks.
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
    is_valid: bool
    unsupported_claims: List[str]
    suggested_revision: str
    has_valid_citations: bool


def verify_citation_syntax(citations: List[Citation]) -> bool:
    """Check that citations exist and have realistic page bounds."""
    if not citations:
        return False
    for c in citations:
        if c.page < 1 or c.page > 100:
            return False
        if not c.paper_title or not c.section:
            return False
    return True


def parse_verification_response(raw_text: str, citations: List[Citation]) -> VerificationOutcome:
    """Parse JSON evaluation from verifier LLM."""
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
