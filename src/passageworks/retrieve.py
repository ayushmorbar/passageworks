"""BM25 retrieval engine and tool for Passageworks.

Implements a deterministic, zero-dependency BM25Okapi inverted index
providing fast passage ranking and configurable section-title boosting.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from passageworks.models import PassageChunk, RetrievalResult


def tokenize(text: str) -> list[str]:
    """Tokenize input text using alphanumeric boundary matching and lowercasing.

    Args:
        text: Raw text string to tokenize.

    Returns:
        List of lowercased alphanumeric tokens.
    """
    return [w.lower() for w in re.findall(r"\b[A-Za-z0-9_\-\.]+\b", text)]


class BM25Index:
    """Self-contained Okapi BM25 inverted index for deterministic in-process retrieval.

    Args:
        chunks: List of extracted PassageChunk instances comprising the corpus.
        k1: Term frequency saturation hyperparameter (default 1.5).
        b: Document length normalization hyperparameter (default 0.75).
    """

    def __init__(self, chunks: list[PassageChunk], k1: float = 1.5, b: float = 0.75) -> None:
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self.corpus_size = len(chunks)
        self.doc_tokens: list[list[str]] = [tokenize(c.text) for c in chunks]
        self.doc_lens: list[int] = [len(toks) for toks in self.doc_tokens]
        self.avg_doc_len: float = (
            sum(self.doc_lens) / self.corpus_size if self.corpus_size > 0 else 0.0
        )

        # Inverted index and term frequencies per document
        self.doc_freqs: dict[str, int] = Counter()
        self.term_freqs: list[Counter[str]] = []

        for toks in self.doc_tokens:
            tf: Counter[str] = Counter(toks)
            self.term_freqs.append(tf)
            for term in tf.keys():
                self.doc_freqs[term] += 1

        # Precompute Robertson-Spärck Jones IDF
        self.idf: dict[str, float] = {}
        for term, df in self.doc_freqs.items():
            self.idf[term] = math.log((self.corpus_size - df + 0.5) / (df + 0.5) + 1.0)

    def score(self, query_tokens: list[str], doc_idx: int) -> float:
        """Compute the BM25 score for a document given a tokenized query.

        Args:
            query_tokens: List of tokenized query keywords.
            doc_idx: Index of document in the corpus.

        Returns:
            Calculated floating-point BM25 score.
        """
        score = 0.0
        doc_len = self.doc_lens[doc_idx]
        tf_dict = self.term_freqs[doc_idx]

        for q in query_tokens:
            if q not in tf_dict:
                continue
            f = tf_dict[q]
            idf = self.idf.get(q, 0.0)
            numerator = f * (self.k1 + 1.0)
            denominator = f + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len))
            score += idf * (numerator / denominator)

        return score

    def search(
        self,
        query: str,
        top_k: int = 5,
        boost_sections: bool = False,
    ) -> list[RetrievalResult]:
        """Rank passage chunks against a query.

        Args:
            query: User search query string.
            top_k: Number of highest-ranked results to return.
            boost_sections: When True, boosts document score by 20% per matching section token.

        Returns:
            List of RetrievalResult instances sorted in descending order of score.
        """
        q_tokens = tokenize(query)
        if not q_tokens:
            return []

        scores: list[tuple[int, float]] = []
        for idx in range(self.corpus_size):
            base_score = self.score(q_tokens, idx)
            if base_score <= 0.0:
                continue

            final_score = base_score
            if boost_sections:
                sec_tokens = set(tokenize(self.chunks[idx].section_title))
                matches = sum(1 for q in q_tokens if q in sec_tokens)
                if matches > 0:
                    final_score *= 1.0 + (0.2 * matches)

            scores.append((idx, final_score))

        # Sort descending by relevance score
        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, s in scores[:top_k]:
            results.append(RetrievalResult(chunk=self.chunks[idx], score=round(s, 4)))

        return results


class RetrieverTool:
    """Passageworks retrieval service supporting configurable retrieval settings.

    Args:
        chunks_path: File path to the pre-extracted JSON Lines chunks file.
    """

    def __init__(self, chunks_path: Path) -> None:
        self.chunks: list[PassageChunk] = []
        if chunks_path.exists():
            with open(chunks_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self.chunks.append(PassageChunk.from_dict(json.loads(line)))

        self.index = BM25Index(self.chunks)

    def retrieve(
        self,
        query: str,
        setting: str = "setting_a",
    ) -> list[RetrievalResult]:
        """Retrieve passages under a specified experimental setting.

        Args:
            query: User natural-language question.
            setting: Retrieval configuration ID:
                - 'setting_a': Standard top-5 passages, no reranking.
                - 'setting_b': Compact top-3 passages, no reranking (lower token footprint).
                - 'setting_c': Top-5 passages with section-title rerank boosting.

        Returns:
            List of RetrievalResult instances meeting the specified setting criteria.
        """
        if setting == "setting_b":
            return self.index.search(query=query, top_k=3, boost_sections=False)
        elif setting == "setting_c":
            return self.index.search(query=query, top_k=5, boost_sections=True)
        else:  # default setting_a
            return self.index.search(query=query, top_k=5, boost_sections=False)
