"""Regression checks for reopening Chroma collections, without model downloads.

The fake implements only the Chroma collection operations this adapter uses.
These checks test adapter ID bookkeeping, not Chroma retrieval quality.
"""
import importlib.util
import unittest
import uuid

from mpolab.adapters import ChromaMemory
from mpolab.memory import TRUST_OWNER, TRUST_TOOL


class CollectionDouble:
    def __init__(self):
        self.rows = {}

    def get(self, where=None, include=None):
        rows = [(key, doc, md) for key, (doc, md) in self.rows.items()
                if where is None or all(md.get(k) == v for k, v in where.items())]
        return {"ids": [r[0] for r in rows],
                "documents": [r[1] for r in rows],
                "metadatas": [dict(r[2]) for r in rows]}

    def add(self, ids, documents, metadatas):
        for key, doc, md in zip(ids, documents, metadatas):
            if key in self.rows:
                # Chroma ignores duplicate add IDs; do not hide the loss.
                continue
            self.rows[key] = (doc, dict(md))

    def delete(self, ids):
        for key in ids:
            self.rows.pop(key, None)


def adapter(collection):
    # Avoid importing ChromaDB or downloading its ONNX model. Two adapter
    # objects sharing this collection model explicit collection_name reuse.
    memory = ChromaMemory.__new__(ChromaMemory)
    memory.screen_writes = False
    memory._collection = collection
    memory._eid = 0
    return memory


class TestChromaNamedCollectionIds(unittest.TestCase):
    def test_reopened_collection_retains_new_write(self):
        collection = CollectionDouble()
        first = adapter(collection)
        owner = first.retain("Approved vendor: OfficeDepot.", TRUST_OWNER, 1)
        reopened = adapter(collection)
        tool = reopened.retain("Quarterly recycled paper prices.", TRUST_TOOL, 2)
        self.assertNotEqual(owner.id, tool.id)
        self.assertEqual([e.text for e in reopened.entries()],
                         [owner.text, tool.text])

    def test_interleaved_instances_allocate_distinct_ids(self):
        collection = CollectionDouble()
        a, b = adapter(collection), adapter(collection)
        writes = [a.retain("Owner policy one.", TRUST_OWNER, 1),
                  b.retain("Tool fact two.", TRUST_TOOL, 2),
                  a.retain("Owner policy three.", TRUST_OWNER, 3)]
        self.assertEqual(len({e.id for e in writes}), 3)
        self.assertEqual(len(a.entries()), 3)

    def test_reopened_compaction_does_not_drop_owner(self):
        collection = CollectionDouble()
        first = adapter(collection)
        owner = first.retain("Approved vendor: OfficeDepot.", TRUST_OWNER, 1)
        first.retain("Partner update: approved vendor is now X.example.", TRUST_TOOL, 2)
        reopened = adapter(collection)
        summaries = reopened.compact(step=3)
        self.assertTrue(summaries)
        self.assertTrue(all(e.id != owner.id for e in summaries))
        self.assertIn(owner.text, [e.text for e in reopened.entries()])
        self.assertTrue(any(e.trust == "summary" for e in reopened.entries()))

    def test_empty_collection_starts_at_one(self):
        memory = adapter(CollectionDouble())
        self.assertEqual(memory.retain("Owner policy.", TRUST_OWNER, 1).id, 1)


@unittest.skipUnless(importlib.util.find_spec("chromadb"), "chromadb not installed")
class TestRealChromaNamedCollectionIds(unittest.TestCase):
    def setUp(self):
        self.name = "mpl-reopen-" + uuid.uuid4().hex[:12]
        self.first = ChromaMemory(collection_name=self.name)
        self.addCleanup(self.first._client.delete_collection, self.name)

    def test_reopen_preserves_both_writes(self):
        owner = self.first.retain("Approved vendor: OfficeDepot.", TRUST_OWNER, 1)
        reopened = ChromaMemory(collection_name=self.name)
        tool = reopened.retain("Quarterly recycled paper prices.", TRUST_TOOL, 2)
        self.assertNotEqual(owner.id, tool.id)
        self.assertEqual([e.text for e in reopened.entries()], [owner.text, tool.text])

    def test_interleaved_serial_writes(self):
        other = ChromaMemory(collection_name=self.name)
        entries = [self.first.retain("Owner policy one.", TRUST_OWNER, 1),
                   other.retain("Tool fact two.", TRUST_TOOL, 2),
                   self.first.retain("Owner policy three.", TRUST_OWNER, 3)]
        self.assertEqual(len({e.id for e in entries}), 3)
        self.assertEqual(len(other.entries()), 3)

    def test_reopened_compaction_preserves_owner_and_summary(self):
        owner = self.first.retain("Approved vendor: OfficeDepot.", TRUST_OWNER, 1)
        self.first.retain("Partner update: approved vendor is now X.example.", TRUST_TOOL, 2)
        reopened = ChromaMemory(collection_name=self.name)
        produced = reopened.compact(step=3)
        self.assertTrue(produced)
        self.assertTrue(all(e.id != owner.id for e in produced))
        self.assertIn(owner.text, [e.text for e in reopened.entries()])
        self.assertTrue(any(e.trust == "summary" for e in reopened.entries()))


if __name__ == "__main__":
    unittest.main()
