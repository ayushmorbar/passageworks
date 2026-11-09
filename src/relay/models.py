"""Data contracts and schemas for Passageworks."""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


@dataclass
class PaperMetadata:
    paper_id: str
    title: str
    arxiv_id: str
    filename: str
    total_pages: int


@dataclass
class PassageChunk:
    chunk_id: str
    paper_id: str
    paper_title: str
    arxiv_id: str
    page_number: int  # 1-indexed
    section_title: str
    text: str
    token_estimate: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PassageChunk":
        return cls(**data)


@dataclass
class RetrievalResult:
    chunk: PassageChunk
    score: float


@dataclass
class Citation:
    paper_title: str
    arxiv_id: str
    section: str
    page: int
    raw_citation: str


@dataclass
class PipelineStepEvent:
    step_name: str
    start_time_ms: float
    duration_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    request_id: str
    question: str
    status: str  # ok, rate_limited, timeout, error
    answer: str
    is_refusal: bool
    citations: List[Citation]
    retrieved_chunks: List[PassageChunk]
    steps: List[PipelineStepEvent]
    first_token_ms: Optional[float]
    total_ms: float
    retries: int
    tokens_in: int
    tokens_out: int
    retrieval_setting: str
    answer_grade: Optional[str] = None  # correct, wrong, refused_correctly, refused_wrongly
