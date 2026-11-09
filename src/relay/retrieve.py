"""BM25 retrieval engine and tool for Passageworks."""

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import List, Dict, Tuple

from relay.models import PassageChunk, RetrievalResult


def tokenize(text: str) -> List[str]:
    """Simple alphanumeric tokenization with lowercasing."""
    return [w.lower() for w in re.findall(r"\b[A-Za-z0-9_\-\.]+\b", text)]


class BM25Index:
    """Self-contained BM25Okapi implementation for local, zero-dependency reproducibility."""

    def __init__(self, chunks: List[PassageChunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self.corpus_size = len(chunks)
        self.doc_tokens: List[List[str]] = [tokenize(c.text) for c in chunks]
        self.doc_lens: List[int] = [len(toks) for toks in self.doc_tokens]
        self.avg_doc_len: float = (
            sum(self.doc_lens) / self.corpus_size if self.corpus_size > 0 else 0.0
        )

        # Inverted index and term frequencies per document
        self.doc_freqs: Dict[str, int] = Counter()
        self.term_freqs: List[Counter] = []

        for toks in self.doc_tokens:
            tf = Counter(toks)
            self.term_freqs.append(tf)
            for term in tf.keys():
                self.doc_freqs[term] += 1

        # Precompute IDF
        self.idf: Dict[str, float] = {}
        for term, df in self.doc_freqs.items():
            # Standard Robertson-Spärck Jones IDF
            self.idf[term] = math.log((self.corpus_size - df + 0.5) / (df + 0.5) + 1.0)

    def score(self, query_tokens: List[str], doc_idx: int) -> float:
        """Compute BM25 score for a document given tokenized query."""
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
    ) -> List[RetrievalResult]:
        """Rank chunks against query. Optionally boost scores if query terms appear in section titles."""
        q_tokens = tokenize(query)
        if not q_tokens:
            return []

        scores: List[Tuple[int, float]] = []
        for idx in range(self.corpus_size):
            base_score = self.score(q_tokens, idx)
            if base_score <= 0.0:
                continue

            final_score = base_score
            if boost_sections:
                sec_tokens = set(tokenize(self.chunks[idx].section_title))
                matches = sum(1 for q in q_tokens if q in sec_tokens)
                if matches > 0:
                    final_score *= 1.0 + (0.2 * matches)  # 20% boost per matching section keyword

            scores.append((idx, final_score))

        # Sort descending by score
        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, s in scores[:top_k]:
            results.append(RetrievalResult(chunk=self.chunks[idx], score=round(s, 4)))

        return results


class RetrieverTool:
    """Passageworks retrieval service supporting multiple settings."""

    def __init__(self, chunks_path: Path):
        self.chunks: List[PassageChunk] = []
        if chunks_path.exists():
            with open(chunks_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self.chunks.append(PassageChunk.from_dict(json.loads(line)))

        self.index = BM25Index(self.chunks)

    def retrieve(
        self,
        query: str,
        setting: str = "setting_a",
    ) -> List[RetrievalResult]:
        """Retrieve passages under a specified setting.

        - setting_a: standard top-5 passages, no reranking.
        - setting_b: compact top-3 passages, no reranking (lower token footprint).
        - setting_c: top-5 passages with section-title rerank boosting.
        """
        if setting == "setting_b":
            return self.index.search(query=query, top_k=3, boost_sections=False)
        elif setting == "setting_c":
            return self.index.search(query=query, top_k=5, boost_sections=True)
        else:  # default setting_a
            return self.index.search(query=query, top_k=5, boost_sections=False)
