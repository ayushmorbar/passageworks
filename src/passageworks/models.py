"""Data contracts and schemas for the Passageworks pipeline.

Defines typed dataclasses for paper metadata, passage chunks, retrieval results,
inline citations, step telemetry events, and pipeline execution results.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PaperMetadata:
    """Metadata describing a source research paper in the knowledge library.

    Attributes:
        paper_id: Short unique identifier (e.g. 'attention', 'moshi', 'dynamic_chunking').
        title: Full formal academic title of the paper.
        arxiv_id: arXiv identifier string including version.
        filename: Base PDF filename on disk.
        total_pages: Total number of pages in the PDF document.
    """

    paper_id: str
    title: str
    arxiv_id: str
    filename: str
    total_pages: int


@dataclass
class PassageChunk:
    """An extracted, contextualized text segment from a research paper.

    Attributes:
        chunk_id: Globally unique sequential chunk identifier (e.g. 'attention_p01_c001').
        paper_id: Short paper identifier.
        paper_title: Full paper title for citation generation.
        arxiv_id: arXiv identifier for citation generation.
        page_number: 1-indexed document page number where the chunk begins.
        section_title: Heading of the containing section or subsection.
        text: Raw textual content of the extracted excerpt.
        token_estimate: Heuristic word/token count estimate for budgeting.
    """

    chunk_id: str
    paper_id: str
    paper_title: str
    arxiv_id: str
    page_number: int
    section_title: str
    text: str
    token_estimate: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert chunk instance to a JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PassageChunk:
        """Instantiate a PassageChunk from a deserialized dictionary."""
        return cls(**data)


@dataclass
class RetrievalResult:
    """Ranked passage result returned by the BM25 retrieval tool.

    Attributes:
        chunk: The retrieved passage chunk.
        score: Computed Okapi BM25 relevance score.
    """

    chunk: PassageChunk
    score: float


@dataclass
class Citation:
    """Structured representation of an inline paper citation.

    Attributes:
        paper_title: Title of the cited paper.
        arxiv_id: arXiv identifier of the cited paper.
        section: Section name or number where evidence was located.
        page: 1-indexed page number of the cited evidence.
        raw_citation: The exact bracketed string extracted from text (e.g. '[Paper, Section, Page]').
    """

    paper_title: str
    arxiv_id: str
    section: str
    page: int
    raw_citation: str


@dataclass
class PipelineStepEvent:
    """Telemetry record for an individual pipeline execution stage.

    Attributes:
        step_name: Identifier for the stage ('CLASSIFY', 'RETRIEVE', 'DRAFT', 'VERIFY_LOOP_0', etc.).
        start_time_ms: Milliseconds elapsed from request arrival to step commencement.
        duration_ms: Duration of this step in milliseconds.
        tokens_in: Prompt tokens consumed during this step.
        tokens_out: Completion tokens emitted during this step.
        details: Optional dictionary containing stage-specific diagnostic metadata.
    """

    step_name: str
    start_time_ms: float
    duration_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Final output and comprehensive audit trail for a processed question.

    Attributes:
        request_id: Unique request identifier.
        question: User query string.
        status: Execution status ('ok', 'rate_limited', 'timeout', 'error').
        answer: Final generated answer or polite refusal string.
        is_refusal: True if the pipeline declined to provide a factual answer.
        citations: List of structured citations extracted from the verified answer.
        retrieved_chunks: Passage chunks retrieved during execution.
        steps: Chronological list of pipeline stage telemetry events.
        first_token_ms: Latency in ms to the first verified answer token (or total_ms if buffered).
        total_ms: Total end-to-end elapsed request duration in milliseconds.
        retries: Total upstream provider retries consumed across all steps.
        tokens_in: Cumulative prompt tokens expended across all steps.
        tokens_out: Cumulative completion tokens generated across all steps.
        retrieval_setting: Retrieval configuration evaluated ('setting_a', 'setting_b', 'setting_c').
        answer_grade: Category required by evaluation brief ('correct', 'wrong', 'refused_correctly', 'refused_wrongly').
    """

    request_id: str
    question: str
    status: str
    answer: str
    is_refusal: bool
    citations: list[Citation]
    retrieved_chunks: list[PassageChunk]
    steps: list[PipelineStepEvent]
    first_token_ms: float | None
    total_ms: float
    retries: int
    tokens_in: int
    tokens_out: int
    retrieval_setting: str
    answer_grade: str | None = None
