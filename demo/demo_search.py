"""In-memory re-implementation of the retrieval step, for the public demo only.

Same as production: the synthetic corpus (app/eval/corpus.py), the production chunker
(app/services/chunking.py), the same embedding model and text format, the role-to-group
permission matrix applied BEFORE ranking, hybrid ranking with RRF k=60, top 5, and the
0.35 cosine-distance evidence gate.

Different from production: vectors live in memory instead of PostgreSQL/pgvector, and the
keyword side approximates PostgreSQL full-text search (English stop words, light stemming,
all terms required) instead of calling websearch_to_tsquery / ts_rank_cd.
"""
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.eval.corpus import CORPUS_VERSION, DOCS  # noqa: E402
from app.services.chunking import PageInput, chunk_pages  # noqa: E402

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
RRF_K = 60
CANDIDATES = 20
TOP_K = 5
MAX_DISTANCE = 0.35

# Alex's approved permission matrix (migration 94a1fedfb71d).
ROLE_GROUPS = {
    "hr": ("general", "hr"),
    "support": ("general", "support"),
    "operations": ("general", "support", "operations"),
}
ROLE_LABEL = {"hr": "HR staff", "support": "Support agent", "operations": "Operations staff"}
GROUP_LABEL = {"general": "General", "hr": "HR", "support": "Support", "operations": "Operations"}

_STOP = set("""a about above after again against all am an and any are as at be because been before
being below between both but by can did do does doing down during each few for from further had has
have having he her here hers herself him himself his how i if in into is it its itself just me more
most my myself no nor not now of off on once only or other our ours ourselves out over own same she
should so some such than that the their theirs them themselves then there these they this those
through to too under until up very was we were what when where which while who whom why will with
you your yours yourself yourselves""".split())
_WORD = re.compile(r"[a-z0-9]+(?:[.,:][0-9]+)*")


def _stem(w: str) -> str:
    for suf in ("ations", "ation", "ings", "ing", "edly", "ed", "ies", "es", "s", "ly"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def terms(text: str) -> list[str]:
    return [_stem(w) for w in _WORD.findall(text.lower()) if w not in _STOP]


@dataclass
class Chunk:
    id: int
    document_title: str
    group: str
    page_number: int
    heading: str | None
    text: str
    low_confidence: bool
    page_text: str


def build_chunks() -> list[Chunk]:
    out = []
    for doc in DOCS:
        pages = [PageInput(n, "\n".join(lines), is_ocr=doc["scanned"])
                 for n, lines in enumerate(doc["pages"], start=1)]
        page_text = {p.page_number: p.text for p in pages}
        for c in chunk_pages(pages):
            out.append(Chunk(len(out), doc["title"], doc["group"], c.page_number, c.heading,
                             c.text, c.low_confidence, page_text[c.page_number]))
    return out


class Index:
    def __init__(self, embed_documents, embed_query):
        """embed_documents(list[str]) -> 2-D array; embed_query(str) -> 1-D array (normalised)."""
        import numpy as np
        self.np = np
        self.chunks = build_chunks()
        texts = [f"{c.document_title}\n{c.heading or ''}\n{c.text}" for c in self.chunks]
        m = np.asarray(embed_documents(texts), dtype=np.float32)
        self.matrix = m / np.linalg.norm(m, axis=1, keepdims=True)
        self.embed_query = embed_query
        self.kw = [terms(f"{c.heading or ''} {c.text}") for c in self.chunks]

    def search(self, query: str, role: str, k: int = TOP_K) -> list[dict]:
        np = self.np
        groups = set(ROLE_GROUPS[role])
        visible = [c.id for c in self.chunks if c.group in groups]  # filter first, then rank
        if not visible:
            return []
        q = np.asarray(self.embed_query(BGE_QUERY_PREFIX + query), dtype=np.float32)
        q = q / np.linalg.norm(q)
        dist = 1.0 - self.matrix[visible] @ q
        order = np.argsort(dist)[:CANDIDATES]
        vector_ids = [visible[i] for i in order]
        vdist = {visible[i]: float(dist[i]) for i in order}

        qterms = set(terms(query))
        kw_hits = []
        if qterms:
            for cid in visible:
                toks = self.kw[cid]
                if qterms <= set(toks):
                    kw_hits.append((sum(toks.count(t) for t in qterms), cid))
        keyword_ids = [cid for _, cid in sorted(kw_hits, reverse=True)[:CANDIDATES]]

        scores, vrank, krank = {}, {}, {}
        for rank, cid in enumerate(vector_ids, start=1):
            scores[cid] = scores.get(cid, 0) + 1 / (RRF_K + rank)
            vrank[cid] = rank
        for rank, cid in enumerate(keyword_ids, start=1):
            scores[cid] = scores.get(cid, 0) + 1 / (RRF_K + rank)
            krank[cid] = rank
        top = sorted(scores, key=scores.get, reverse=True)[:k]
        return [{
            "chunk": self.chunks[cid], "score": round(scores[cid], 5),
            "vector_rank": vrank.get(cid), "keyword_rank": krank.get(cid),
            "distance": round(vdist[cid], 4) if cid in vdist else None,
        } for cid in top]


def gate(results: list[dict]) -> tuple[bool, float | None]:
    ds = [r["distance"] for r in results if r["distance"] is not None]
    best = min(ds) if ds else None
    return (best is not None and best <= MAX_DISTANCE), best


def documents():
    return [{"title": d["title"], "group": d["group"], "pages": len(d["pages"]),
             "scanned": d["scanned"], "superseded_version": "old_pages" in d} for d in DOCS]


__all__ = ["Index", "gate", "documents", "ROLE_GROUPS", "ROLE_LABEL", "GROUP_LABEL",
           "CORPUS_VERSION", "EMBEDDING_MODEL", "MAX_DISTANCE"]
