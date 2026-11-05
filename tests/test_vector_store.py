"""Chroma 向量库增删查验证：临时目录 + FakeEmbeddings，不联网、不需要 API Key。

未安装 langchain-chroma / chromadb 时自动跳过，不影响 Agent Loop 单测。
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from langchain_core.documents import Document
    from langchain_core.embeddings import FakeEmbeddings

    import knowledgebase_server.vector_store as vs

    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


@unittest.skipUnless(HAS_DEPS, "需要 langchain-chroma / chromadb / langchain-openai")
class VectorStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="chroma_test_")
        self._original = (vs.KB_DIR, vs.get_embedding)
        vs.KB_DIR = self.tmp
        vs.get_embedding = lambda: FakeEmbeddings(size=8)

    def tearDown(self):
        vs.KB_DIR, vs.get_embedding = self._original
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_search_delete(self):
        docs = [
            Document(
                page_content="千川投流 ROI 止损线为二点五",
                metadata={"source": "notes/qianchuan.md"},
            ),
            Document(
                page_content="Chroma 是持久化向量数据库",
                metadata={"source": "notes/chroma.md"},
            ),
        ]
        self.assertEqual(vs.add_documents("demo", docs), 2)

        hits = vs.search_kb_docs("demo", "千川", k=2)
        self.assertEqual(len(hits), 2)
        # FakeEmbeddings 与语义无关，这里只校验返回结构与来源，不校验排序质量。
        self.assertEqual(
            {h["sources"] for h in hits},
            {"notes/qianchuan.md", "notes/chroma.md"},
        )

        all_hits = vs.search_all_kbs_docs("向量数据库", k=2)
        self.assertTrue(all_hits)
        self.assertEqual(all_hits[0]["kb_name"], "demo")

        self.assertEqual(vs.delete_by_source("demo", "chroma.md"), 1)
        left = vs.search_kb_docs("demo", "Chroma", k=3)
        self.assertTrue(all("chroma.md" not in h["sources"] for h in left))


if __name__ == "__main__":
    unittest.main(verbosity=2)
