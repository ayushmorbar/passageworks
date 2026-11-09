"""Unit tests for Passageworks BM25 retrieval engine."""

from pathlib import Path

import pytest

from passageworks.retrieve import RetrieverTool


@pytest.fixture(scope="module")
def retriever():
    chunks_path = Path("papers/chunks.jsonl")
    assert chunks_path.exists(), f"Chunks file not found at {chunks_path}"
    return RetrieverTool(chunks_path)


def test_retrieval_attention_paper(retriever):
    query = "scaled dot-product attention multi-head mechanism"
    results = retriever.retrieve(query, setting="setting_a")

    assert len(results) == 5
    top_result = results[0]
    assert top_result.score > 0
    # Must retrieve from Attention Is All You Need
    assert top_result.chunk.paper_id == "attention"
    assert "arXiv:1706.03762v7" in top_result.chunk.arxiv_id


def test_retrieval_moshi_paper(retriever):
    query = "Moshi real-time dialogue speech text Mimi codec Kyutai"
    results = retriever.retrieve(query, setting="setting_a")

    assert len(results) == 5
    top_result = results[0]
    assert top_result.score > 0
    assert top_result.chunk.paper_id == "moshi"
    assert "arXiv:2410.00037v1" in top_result.chunk.arxiv_id


def test_retrieval_dynamic_chunking_paper(retriever):
    query = "dynamic chunking end-to-end hierarchical sequence modeling"
    results = retriever.retrieve(query, setting="setting_a")

    assert len(results) == 5
    top_result = results[0]
    assert top_result.score > 0
    assert top_result.chunk.paper_id == "dynamic_chunking"
    assert "arXiv:2507.07955v2" in top_result.chunk.arxiv_id


def test_retrieval_settings(retriever):
    query = "transformer encoder decoder attention layers"

    # Setting A: default top-5
    res_a = retriever.retrieve(query, setting="setting_a")
    assert len(res_a) == 5

    # Setting B: compact top-3
    res_b = retriever.retrieve(query, setting="setting_b")
    assert len(res_b) == 3

    # Setting C: section boosted top-5
    res_c = retriever.retrieve(query, setting="setting_c")
    assert len(res_c) == 5


def test_chunk_metadata_completeness(retriever):
    results = retriever.retrieve("neural network sequence model", setting="setting_a")
    for r in results:
        c = r.chunk
        assert c.chunk_id.startswith(("attention_", "moshi_", "dynamic_chunking_"))
        assert c.page_number >= 1
        assert len(c.section_title) > 0
        assert len(c.text) > 20
        assert c.token_estimate > 0
