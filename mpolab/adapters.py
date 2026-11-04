"""Third-party memory backend adapters.

ChromaMemory runs the whole test range against ChromaDB, a real
vector database, with its default embedding model (all-MiniLM-L6-v2)
executing locally via ONNX Runtime - no server, no API key, no paid
calls. After a one-time model download it works fully offline.

The adapter implements the same contract as ReferenceMemory
(retain / recall / compact / delete / repair), so every scenario and
every conformance test runs against both backends unchanged. That is
the point: the attacks and defenses are properties of the memory
contract, not of one implementation.
"""

from __future__ import annotations

from .memory import MemoryEntry, TRUST_OWNER, TRUST_TOOL, _norm, classify, INSTRUCTION_LIKE
from .policy import compact_plan, repair_plan


class ChromaMemory:
    """ChromaDB-backed memory with local ONNX embeddings.

    Collection semantics: with no collection_name, every instance gets
    its own unique collection - episodes can never leak between two
    default instances or across test runs. Passing collection_name is
    an explicit opt-in to reuse: the named collection is opened with
    get_or_create and shared by every instance that names it.
    """

    def __init__(self, screen_writes: bool = False, collection_name: str | None = None):
        import uuid

        import chromadb  # lazy: the core range stays stdlib-only

        self.screen_writes = screen_writes
        self._client = chromadb.Client()
        if collection_name is None:
            self._collection = self._client.create_collection(f"mpl-{uuid.uuid4().hex[:12]}")
        else:
            self._collection = self._client.get_or_create_collection(collection_name)
        self._eid = 0

    def _next_eid(self) -> int:
        self._eid += 1
        return self._eid

    @staticmethod
    def _to_entry(doc_id: str, document: str, md: dict) -> MemoryEntry:
        return MemoryEntry(
            id=int(md["eid"]),
            text=document,
            trust=md["trust"],
            origin=md["origin"],
            kind=md["kind"],
            step=int(md["step"]),
            confidence=float(md["confidence"]),
            quarantined=bool(md["quarantined"]),
            source=md.get("source", ""),
        )

    def _all_rows(self):
        got = self._collection.get(include=["documents", "metadatas"])
        return [
            self._to_entry(cid, doc, md)
            for cid, doc, md in zip(got["ids"], got["documents"], got["metadatas"])
        ]

    def retain(self, text: str, trust: str, step: int, source: str = "") -> MemoryEntry:
        norm = _norm(text)
        existing = self._collection.get(where={"norm": norm}, include=["documents", "metadatas"])
        if existing["ids"]:
            cid = existing["ids"][0]
            md = dict(existing["metadatas"][0])
            md["confidence"] = float(md["confidence"]) + 0.5
            self._collection.update(ids=[cid], metadatas=[md])
            return self._to_entry(cid, existing["documents"][0], md)
        eid = self._next_eid()
        quarantined = bool(
            self.screen_writes and trust == TRUST_TOOL and INSTRUCTION_LIKE.search(text)
        )
        md = {
            "eid": eid,
            "trust": trust,
            "origin": trust,
            "kind": classify(text),
            "step": int(step),
            "confidence": 1.0,
            "quarantined": quarantined,
            "source": source,
            "norm": norm,
        }
        self._collection.add(ids=[f"e{eid}"], documents=[text], metadatas=[md])
        return self._to_entry(f"e{eid}", text, md)

    def recall(self, query: str, k: int = 5, include_quarantined: bool = False) -> list[MemoryEntry]:
        count = self._collection.count()
        if count == 0:
            return []
        res = self._collection.query(query_texts=[query], n_results=count)
        rows = [
            self._to_entry(cid, doc, md)
            for cid, doc, md in zip(res["ids"][0], res["documents"][0], res["metadatas"][0])
        ]
        distances = res["distances"][0]
        scored = []
        for entry, dist in zip(rows, distances):
            if entry.quarantined and not include_quarantined:
                continue
            score = -float(dist) + 0.05 * entry.confidence
            scored.append((score, entry))
        scored.sort(key=lambda item: (-item[0], item[1].id))
        return [entry for _, entry in scored[:k]]

    def compact(self, step: int) -> list[MemoryEntry]:
        entries = sorted(self._all_rows(), key=lambda e: e.id)
        summaries, drop = compact_plan(entries, step, self._eid + 1)
        if drop:
            self._collection.delete(ids=[f"e{i}" for i in drop])
        produced = []
        for spec in summaries:
            md = {
                "eid": spec["id"],
                "trust": spec["trust"],
                "origin": spec["origin"],
                "kind": spec["kind"],
                "step": spec["step"],
                "confidence": spec["confidence"],
                "quarantined": False,
                "source": spec["source"],
                "norm": _norm(spec["text"]),
            }
            self._collection.add(ids=[f"e{spec['id']}"], documents=[spec["text"]], metadatas=[md])
            produced.append(self._to_entry(f"e{spec['id']}", spec["text"], md))
            self._eid = max(self._eid, spec["id"])
        return produced

    def entries(self, include_quarantined: bool = True) -> list[MemoryEntry]:
        rows = sorted(self._all_rows(), key=lambda e: e.id)
        if include_quarantined:
            return rows
        return [e for e in rows if not e.quarantined]

    def delete(self, entry_id: int) -> bool:
        before = self._collection.count()
        self._collection.delete(ids=[f"e{entry_id}"])
        return self._collection.count() != before

    def repair(self) -> list[int]:
        """Conflict-scoped repair, identical policy to ReferenceMemory."""
        removed = repair_plan(self._all_rows())
        if removed:
            self._collection.delete(ids=[f"e{i}" for i in removed])
        return removed


class SQLiteVecMemory:
    """sqlite-vec-backed memory: approximate nearest-neighbour recall
    inside SQLite, no server and no model download.

    Embeddings are a deterministic hashed bag-of-words (stdlib only):
    every token updates one fixed dimension, then the vector is
    L2-normalized. That keeps this adapter offline and reproducible
    while still exercising real ANN recall plumbing in sqlite-vec.
    It does not measure semantic embedding quality - ChromaMemory's
    ONNX model is the realistic-embedding backend.

    Every instance gets its own in-memory database, so episodes can
    never leak between instances or across test runs.
    """

    DIMS = 256

    def __init__(self, screen_writes: bool = False):
        import hashlib  # noqa: F401 - used by _embed
        import sqlite3

        import sqlite_vec  # lazy: the core range stays stdlib-only

        self.screen_writes = screen_writes
        self._db = sqlite3.connect(":memory:")
        self._db.enable_load_extension(True)
        sqlite_vec.load(self._db)
        self._db.enable_load_extension(False)
        self._db.execute(
            "CREATE TABLE entries ("
            "eid INTEGER PRIMARY KEY, text TEXT, trust TEXT, origin TEXT,"
            " kind TEXT, step INTEGER, confidence REAL, quarantined INTEGER,"
            " source TEXT, norm TEXT)"
        )
        self._db.execute(
            f"CREATE VIRTUAL TABLE vec_entries USING vec0("
            f"embedding float[{self.DIMS}] distance_metric=cosine)"
        )
        self._eid = 0

    def _next_eid(self) -> int:
        self._eid += 1
        return self._eid

    @staticmethod
    def _embed(text: str) -> list[float]:
        import hashlib
        import math

        vec = [0.0] * SQLiteVecMemory.DIMS
        for tok in _norm(text).split():
            h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:4], "little")
            vec[h % SQLiteVecMemory.DIMS] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    @staticmethod
    def _to_entry(row) -> MemoryEntry:
        (eid, text, trust, origin, kind, step, confidence, quarantined, source, _norm_col) = row
        return MemoryEntry(
            id=int(eid),
            text=text,
            trust=trust,
            origin=origin,
            kind=kind,
            step=int(step),
            confidence=float(confidence),
            quarantined=bool(quarantined),
            source=source or "",
        )

    def _all_rows(self):
        cur = self._db.execute(
            "SELECT eid, text, trust, origin, kind, step, confidence,"
            " quarantined, source, norm FROM entries"
        )
        return [self._to_entry(r) for r in cur.fetchall()]

    def _insert(self, eid: int, text: str, md: dict) -> None:
        import sqlite_vec

        self._db.execute(
            "INSERT INTO entries (eid, text, trust, origin, kind, step,"
            " confidence, quarantined, source, norm)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                eid, text, md["trust"], md["origin"], md["kind"], md["step"],
                md["confidence"], int(md["quarantined"]), md["source"], md["norm"],
            ),
        )
        self._db.execute(
            "INSERT INTO vec_entries(rowid, embedding) VALUES (?, ?)",
            (eid, sqlite_vec.serialize_float32(self._embed(text))),
        )
        self._db.commit()

    def retain(self, text: str, trust: str, step: int, source: str = "") -> MemoryEntry:
        norm = _norm(text)
        cur = self._db.execute(
            "SELECT eid, text, trust, origin, kind, step, confidence,"
            " quarantined, source, norm FROM entries WHERE norm = ?",
            (norm,),
        )
        existing = cur.fetchone()
        if existing:
            eid = existing[0]
            self._db.execute(
                "UPDATE entries SET confidence = confidence + 0.5 WHERE eid = ?",
                (eid,),
            )
            self._db.commit()
            row = list(existing)
            row[6] = float(row[6]) + 0.5
            return self._to_entry(row)
        eid = self._next_eid()
        quarantined = bool(
            self.screen_writes and trust == TRUST_TOOL and INSTRUCTION_LIKE.search(text)
        )
        md = {
            "trust": trust,
            "origin": trust,
            "kind": classify(text),
            "step": int(step),
            "confidence": 1.0,
            "quarantined": quarantined,
            "source": source,
            "norm": norm,
        }
        self._insert(eid, text, md)
        return self._to_entry(
            (eid, text, md["trust"], md["origin"], md["kind"], md["step"],
             md["confidence"], int(md["quarantined"]), md["source"], md["norm"])
        )

    def recall(self, query: str, k: int = 5, include_quarantined: bool = False) -> list[MemoryEntry]:
        import sqlite_vec

        count = self._db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        if count == 0:
            return []
        cur = self._db.execute(
            "SELECT v.rowid, v.distance FROM vec_entries v"
            " WHERE v.embedding MATCH ? AND k = ?",
            (sqlite_vec.serialize_float32(self._embed(query)), count),
        )
        scored = []
        for rowid, dist in cur.fetchall():
            entry_cur = self._db.execute(
                "SELECT eid, text, trust, origin, kind, step, confidence,"
                " quarantined, source, norm FROM entries WHERE eid = ?",
                (rowid,),
            )
            entry = self._to_entry(entry_cur.fetchone())
            if entry.quarantined and not include_quarantined:
                continue
            score = -float(dist) + 0.05 * entry.confidence
            scored.append((score, entry))
        scored.sort(key=lambda item: (-item[0], item[1].id))
        return [entry for _, entry in scored[:k]]

    def compact(self, step: int) -> list[MemoryEntry]:
        entries = sorted(self._all_rows(), key=lambda e: e.id)
        summaries, drop = compact_plan(entries, step, self._eid + 1)
        produced = []
        for spec in summaries:
            md = {
                "trust": spec["trust"],
                "origin": spec["origin"],
                "kind": spec["kind"],
                "step": spec["step"],
                "confidence": spec["confidence"],
                "quarantined": False,
                "source": spec["source"],
                "norm": _norm(spec["text"]),
            }
            self._insert(spec["id"], spec["text"], md)
            produced.append(self._to_entry(
                (spec["id"], spec["text"], md["trust"], md["origin"], md["kind"],
                 md["step"], md["confidence"], 0, md["source"], md["norm"])
            ))
            self._eid = max(self._eid, spec["id"])
        if drop:
            self._delete_ids(drop)
        return produced

    def entries(self, include_quarantined: bool = True) -> list[MemoryEntry]:
        rows = sorted(self._all_rows(), key=lambda e: e.id)
        if include_quarantined:
            return rows
        return [e for e in rows if not e.quarantined]

    def _delete_ids(self, ids) -> None:
        self._db.executemany("DELETE FROM entries WHERE eid = ?", [(i,) for i in ids])
        self._db.executemany("DELETE FROM vec_entries WHERE rowid = ?", [(i,) for i in ids])
        self._db.commit()

    def delete(self, entry_id: int) -> bool:
        before = self._db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        self._delete_ids([entry_id])
        return self._db.execute("SELECT COUNT(*) FROM entries").fetchone()[0] != before

    def repair(self) -> list[int]:
        """Conflict-scoped repair, identical policy to ReferenceMemory."""
        removed = repair_plan(self._all_rows())
        if removed:
            self._delete_ids(removed)
        return removed
