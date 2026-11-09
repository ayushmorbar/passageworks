"""Inspect page count and initial text samples from the three library papers."""

from pathlib import Path

from pypdf import PdfReader

PAPERS = [
    {
        "id": "attention_v7",
        "title": "Attention Is All You Need",
        "arxiv": "arXiv:1706.03762v7",
        "file": "1706.03762v7.pdf",
    },
    {
        "id": "moshi_v1",
        "title": "Moshi: a speech-text foundation model for real-time dialogue",
        "arxiv": "arXiv:2410.00037v1",
        "file": "Moshi 2410.00037v1.pdf",
    },
    {
        "id": "dynamic_chunking_v2",
        "title": "Dynamic Chunking for End-to-End Hierarchical Sequence Modeling",
        "arxiv": "arXiv:2507.07955v2",
        "file": "Dynamic Chunking for E2E Hierarchical Sequence Modeling 2507.07955v2.pdf",
    },
]


def inspect():
    root = Path(".")
    for p in PAPERS:
        fpath = root / p["file"]
        if not fpath.exists():
            print(f"[MISSING] {p['file']}")
            continue
        reader = PdfReader(str(fpath))
        num_pages = len(reader.pages)
        first_page_text = reader.pages[0].extract_text()
        print("\n==========================================")
        print(f"Paper: {p['title']}")
        print(f"File: {p['file']} | Pages: {num_pages} | Version: {p['arxiv']}")
        safe_preview = (
            first_page_text[:300].encode("ascii", errors="backslashreplace").decode("ascii")
        )
        print(f"First 300 chars of page 1:\n{safe_preview.strip()}")


if __name__ == "__main__":
    inspect()
