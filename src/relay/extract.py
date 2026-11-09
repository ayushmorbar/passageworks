"""PDF extraction and passage chunking for Passageworks restricted library."""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple
from pypdf import PdfReader

from relay.models import PassageChunk, PaperMetadata

PAPERS_INFO = [
    PaperMetadata(
        paper_id="attention",
        title="Attention Is All You Need",
        arxiv_id="arXiv:1706.03762v7",
        filename="1706.03762v7.pdf",
        total_pages=15,
    ),
    PaperMetadata(
        paper_id="moshi",
        title="Moshi: a speech-text foundation model for real-time dialogue",
        arxiv_id="arXiv:2410.00037v1",
        filename="Moshi 2410.00037v1.pdf",
        total_pages=66,
    ),
    PaperMetadata(
        paper_id="dynamic_chunking",
        title="Dynamic Chunking for End-to-End Hierarchical Sequence Modeling",
        arxiv_id="arXiv:2507.07955v2",
        filename="Dynamic Chunking for E2E Hierarchical Sequence Modeling 2507.07955v2.pdf",
        total_pages=39,
    ),
]

SECTION_PATTERN = re.compile(
    r"^(?:(?:\d+\.?\d*)\s+[A-Z][A-Za-z0-9\s,\-:]{2,60}|Abstract|Introduction|Background|Architecture|Conclusion|Related Work|References|Appendix(?:\s+[A-Z])?)\s*$",
    re.MULTILINE,
)


def clean_text(raw_text: str) -> str:
    """Normalize whitespace and filter common PDF artifact lines."""
    lines = []
    for line in raw_text.splitlines():
        trimmed = line.strip()
        # Filter common arXiv footer/header artifacts
        if re.search(r"arXiv:\d{4}\.\d{4,5}v\d", trimmed):
            continue
        if re.match(r"^\d+\s*$", trimmed):  # Standalone page number line
            continue
        if trimmed:
            lines.append(trimmed)
    return "\n".join(lines)


def detect_sections(text: str) -> List[Tuple[str, str]]:
    """Split text into (section_title, section_text) blocks."""
    matches = list(SECTION_PATTERN.finditer(text))
    if not matches:
        return [("General", text)]

    blocks = []
    # Content before first detected section
    first_start = matches[0].start()
    if first_start > 0:
        preamble = text[:first_start].strip()
        if preamble:
            blocks.append(("Preamble", preamble))

    for i, m in enumerate(matches):
        sec_title = m.group(0).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            blocks.append((sec_title, content))

    return blocks


def chunk_text(
    paper: PaperMetadata,
    page_num: int,
    section: str,
    text: str,
    start_chunk_idx: int = 1,
    target_words: int = 250,
    overlap_words: int = 40,
) -> Tuple[List[PassageChunk], int]:
    """Split a section of text into overlapping word windows."""
    words = text.split()
    if not words:
        return [], start_chunk_idx

    chunks = []
    start = 0
    curr_idx = start_chunk_idx

    while start < len(words):
        end = min(start + target_words, len(words))
        chunk_words = words[start:end]
        chunk_str = " ".join(chunk_words)

        chunk_id = f"{paper.paper_id}_p{page_num:02d}_c{curr_idx:03d}"
        est_tokens = int(len(chunk_words) * 1.33)

        chunk = PassageChunk(
            chunk_id=chunk_id,
            paper_id=paper.paper_id,
            paper_title=paper.title,
            arxiv_id=paper.arxiv_id,
            page_number=page_num,
            section_title=section,
            text=chunk_str,
            token_estimate=est_tokens,
        )
        chunks.append(chunk)
        curr_idx += 1

        if end == len(words):
            break
        start += target_words - overlap_words

    return chunks, curr_idx


def extract_all_papers(
    workspace_dir: Path, output_file: Path, report_file: Path
) -> List[PassageChunk]:
    """Process all library papers, generate chunks.jsonl and extraction report."""
    all_chunks: List[PassageChunk] = []
    stats: Dict[str, Dict[str, Any]] = {}

    for paper in PAPERS_INFO:
        pdf_path = workspace_dir / paper.filename
        if not pdf_path.exists():
            print(f"[WARN] Paper file not found: {pdf_path}")
            continue

        reader = PdfReader(str(pdf_path))
        paper_chunks: List[PassageChunk] = []
        current_section = "Abstract"
        chunk_counter = 1

        for page_idx, page in enumerate(reader.pages):
            page_num = page_idx + 1
            raw_text = page.extract_text() or ""
            cleaned = clean_text(raw_text)

            sections = detect_sections(cleaned)
            for sec_title, sec_content in sections:
                if sec_title != "General":
                    current_section = sec_title
                new_chunks, chunk_counter = chunk_text(
                    paper=paper,
                    page_num=page_num,
                    section=current_section,
                    text=sec_content,
                    start_chunk_idx=chunk_counter,
                )
                paper_chunks.extend(new_chunks)

        all_chunks.extend(paper_chunks)
        stats[paper.paper_id] = {
            "title": paper.title,
            "arxiv_id": paper.arxiv_id,
            "pages": len(reader.pages),
            "chunks": len(paper_chunks),
            "total_words": sum(len(c.text.split()) for c in paper_chunks),
            "est_tokens": sum(c.token_estimate for c in paper_chunks),
        }

    # Write chunks.jsonl
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk.to_dict()) + "\n")

    # Write extraction report
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# Library Paper Extraction Report\n\n")
        f.write(f"Total chunks extracted: **{len(all_chunks)}**\n\n")
        f.write("| Paper | arXiv ID | Pages | Chunks | Words | Est. Tokens |\n")
        f.write("|---|---|---|---|---|---|\n")
        for pid, s in stats.items():
            f.write(
                f"| {s['title']} | {s['arxiv_id']} | {s['pages']} | {s['chunks']} | {s['total_words']} | {s['est_tokens']} |\n"
            )

    return all_chunks


if __name__ == "__main__":
    ws = Path(".")
    out_jsonl = Path("papers/chunks.jsonl")
    out_md = Path("papers/extraction_report.md")
    chunks = extract_all_papers(ws, out_jsonl, out_md)
    print(f"Successfully extracted {len(chunks)} chunks to {out_jsonl}")
