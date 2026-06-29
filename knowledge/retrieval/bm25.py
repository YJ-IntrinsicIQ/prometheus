import math
import re
from collections import Counter
from typing import List, Sequence, Tuple


class BM25:
    def __init__(self, documents: Sequence[str], k1: float = 1.5, b: float = 0.75):
        self.documents = [self._normalize(doc) for doc in documents]
        self.k1 = k1
        self.b = b
        self.doc_lengths = [len(doc.split()) for doc in self.documents]
        self.avgdl = sum(self.doc_lengths) / max(1, len(self.documents))
        self.doc_freqs = self._build_doc_freqs(self.documents)
        self.num_docs = len(self.documents)

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.lower()).strip()

    @staticmethod
    def _build_doc_freqs(documents: Sequence[str]) -> dict:
        freqs = {}
        for doc in documents:
            terms = set(doc.split())
            for term in terms:
                freqs[term] = freqs.get(term, 0) + 1
        return freqs

    def score(self, query: str, doc_index: int) -> float:
        query_terms = self._normalize(query).split()
        if not query_terms:
            return 0.0

        doc = self.documents[doc_index]
        doc_terms = Counter(doc.split())
        score = 0.0
        for term in set(query_terms):
            if term not in doc_terms:
                continue
            tf = doc_terms[term]
            df = self.doc_freqs.get(term, 0)
            idf = math.log((self.num_docs - df + 0.5) / (df + 0.5) + 1.0)
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * self.doc_lengths[doc_index] / self.avgdl)
            score += idf * numerator / denominator
        return score

    def scores(self, query: str) -> List[Tuple[int, float]]:
        return [(idx, self.score(query, idx)) for idx in range(self.num_docs)]
