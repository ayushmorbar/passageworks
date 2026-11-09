"""Step 1: Query classification and scope gatekeeping for Passageworks.

Enforces knowledge boundaries by classifying queries against the three permitted
research papers, branching to immediate zero-cost refusal for out-of-scope topics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

CLASSIFIER_PROMPT: str = """You are the scope gatekeeper for Passageworks, a research Q&A assistant restricted exclusively to three arXiv papers:
1. "Attention Is All You Need" (arXiv:1706.03762v7) — Transformer architecture, self-attention, multi-head attention, machine translation.
2. "Moshi: a speech-text foundation model for real-time dialogue" (arXiv:2410.00037v1) — Real-time full-duplex speech-text foundation model, Mimi neural audio codec, Kyutai.
3. "Dynamic Chunking for End-to-End Hierarchical Sequence Modeling" (arXiv:2507.07955v2) — Dynamic chunking, hierarchical sequence modeling, linear RNNs/Transformers, Mamba-2 / SSM backbones in H-Net.

Given the user query, determine whether it can be answered using ONLY these three papers.
- If the question asks about topics outside these three papers (e.g. general world knowledge, external models like GPT-4, cooking, unrelated software), it must be REJECTED.
- If the question is relevant to one or more of these three papers (including Mamba-2/SSM backbones evaluated in the Dynamic Chunking paper), APPROVE it.

Respond in strict JSON with keys:
- "is_in_scope": true / false
- "relevant_paper": "attention" | "moshi" | "dynamic_chunking" | "multiple" | "none"
- "reason": brief 1-sentence justification
"""


@dataclass
class ClassificationDecision:
    """Structured decision output from the scope classification step.

    Attributes:
        is_in_scope: True if query falls within the three-paper knowledge boundary.
        relevant_paper: Identifies the relevant paper or 'multiple'/'none'.
        reason: Brief justification produced by the classifier model.
        refusal_message: Pre-rendered user-facing polite refusal if query is out of scope.
    """

    is_in_scope: bool
    relevant_paper: str
    reason: str
    refusal_message: str | None = None


def parse_classification_response(raw_text: str) -> ClassificationDecision:
    """Parse and validate JSON classification response from the gatekeeper LLM.

    Args:
        raw_text: Raw string output returned by the classifier model.

    Returns:
        ClassificationDecision containing the parsed boolean decision and reasoning.
    """
    try:
        # Strip potential markdown fences
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        data = json.loads(cleaned)
        in_scope = bool(data.get("is_in_scope", False))
        paper = str(data.get("relevant_paper", "none"))
        reason = str(data.get("reason", "No reason provided."))

        refusal = None
        if not in_scope:
            refusal = (
                "I cannot answer this question because it is outside the scope of my restricted library. "
                "I can only answer questions strictly grounded in: "
                "(1) 'Attention Is All You Need' (arXiv:1706.03762v7), "
                "(2) 'Moshi' (arXiv:2410.00037v1), and "
                "(3) 'Dynamic Chunking' (arXiv:2507.07955v2)."
            )

        return ClassificationDecision(
            is_in_scope=in_scope,
            relevant_paper=paper,
            reason=reason,
            refusal_message=refusal,
        )
    except Exception as exc:
        # Fail safe on malformed JSON: reject or treat with caution
        return ClassificationDecision(
            is_in_scope=False,
            relevant_paper="none",
            reason=f"Classification parse error: {exc}",
            refusal_message="Unable to verify whether question is within the allowed paper library.",
        )
