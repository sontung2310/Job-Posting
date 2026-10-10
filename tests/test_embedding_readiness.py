"""Cloud boundaries use saved replies; these tests never send API requests."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import vault_evidence as vault

FIXTURE = ROOT / "tests/fixtures/vault"


class EmbeddingReadinessTests(unittest.TestCase):
    def test_runtime_accepts_only_configured_embedding_model(self):
        with self.assertRaisesRegex(vault.SemanticSearchUnavailable, "text-embedding-3-small"):
            vault.OpenAIEmbeddingModel("generation-model")

    def test_keyword_cli_does_not_import_cloud_packages_or_read_hybrid_config(self):
        with patch.dict(sys.modules, {"openai": None, "chromadb": None, "yaml": None}), redirect_stdout(io.StringIO()) as output:
            code = vault.main(["search", "--vault", str(FIXTURE), "--hybrid-search", "false",
                               "--requirement", "Build RAG systems", "--term", "RAG"])
        self.assertEqual(code, 0)
        self.assertIn("Production RAG", output.getvalue())

    def test_embedding_reply_requires_known_usage_and_complete_indexed_vectors(self):
        reply = SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[0.1, 0.2])],
                                usage=None)
        client = SimpleNamespace(embeddings=SimpleNamespace(create=lambda **kwargs: reply))
        with patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=lambda **kwargs: client)}), patch.dict(os.environ, {"OPENAI_API_KEY": "fixture"}):
            model = vault.OpenAIEmbeddingModel(vault.DEFAULT_EMBEDDING_MODEL)
            with self.assertRaisesRegex(vault.SemanticSearchUnavailable, "usage"):
                model.encode_queries(["saved requirement"])
            reply.usage = SimpleNamespace(prompt_tokens=3, total_tokens=3)
            self.assertEqual(model.encode_queries(["saved requirement"]), [[0.1, 0.2]])
            self.assertEqual(model.usage[-1]["total_tokens"], 3)
            reply.data = [SimpleNamespace(index=1, embedding=[0.1, 0.2])]
            with self.assertRaises(vault.SemanticSearchUnavailable):
                model.encode_queries(["saved requirement"])

    def test_unchanged_index_needs_no_document_embeddings_or_upserts(self):
        notes, _ = vault.scan_vault(FIXTURE)
        candidates = vault.build_candidates(notes)
        collection = SimpleNamespace(
            metadata=vault.chroma_index_metadata(vault.DEFAULT_EMBEDDING_MODEL,
                                                vault.vault_fingerprint(candidates), len(candidates)),
            count=lambda: len(candidates),
        )
        client = SimpleNamespace(get_or_create_collection=lambda **kwargs: collection)
        def forbidden(**kwargs):
            raise AssertionError("Unchanged inputs must not instantiate an embedding client")
        modules = {"chromadb": SimpleNamespace(CloudClient=lambda **kwargs: client),
                   "openai": SimpleNamespace(OpenAI=forbidden)}
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {"CHROMA_API_KEY": "fixture", "OPENAI_API_KEY": "fixture"}):
            self.assertEqual(vault.build_chroma_index(FIXTURE, vault.DEFAULT_EMBEDDING_MODEL), len(candidates))

    def test_current_index_readiness_does_not_send_a_billable_probe(self):
        notes, _ = vault.scan_vault(FIXTURE)
        candidates = vault.build_candidates(notes)
        collection = SimpleNamespace(metadata=vault.chroma_index_metadata(
            vault.DEFAULT_EMBEDDING_MODEL, vault.vault_fingerprint(candidates), len(candidates)),
            count=lambda: len(candidates))
        client = SimpleNamespace(get_collection=lambda **kwargs: collection)
        def forbidden(**kwargs):
            raise AssertionError("Readiness must not submit an embedding probe")
        modules = {"chromadb": SimpleNamespace(CloudClient=lambda **kwargs: client),
                   "openai": SimpleNamespace(OpenAI=lambda **kwargs: SimpleNamespace(
                       embeddings=SimpleNamespace(create=forbidden)))}
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {"CHROMA_API_KEY": "fixture", "OPENAI_API_KEY": "fixture"}), redirect_stdout(io.StringIO()):
            self.assertEqual(vault.run_check_index(FIXTURE, vault.DEFAULT_EMBEDDING_MODEL), 0)
        with patch.dict(sys.modules, {**modules, "openai": None}), redirect_stdout(io.StringIO()):
            with self.assertRaises(vault.SemanticSearchUnavailable):
                vault.run_check_index(FIXTURE, vault.DEFAULT_EMBEDDING_MODEL)

    def test_index_refresh_repairs_missing_vectors_even_when_metadata_matches(self):
        notes, _ = vault.scan_vault(FIXTURE)
        candidates = vault.build_candidates(notes)
        stored = {}
        collection = SimpleNamespace(metadata=vault.chroma_index_metadata(
            vault.DEFAULT_EMBEDDING_MODEL, vault.vault_fingerprint(candidates), len(candidates)),
            count=lambda: len(stored),
            upsert=lambda **kwargs: stored.update(dict(zip(kwargs["ids"], kwargs["embeddings"]))),
            get=lambda **kwargs: {"ids": list(stored)},
            delete=lambda **kwargs: None,
            modify=lambda **kwargs: None)
        def embed(**kwargs):
            return SimpleNamespace(data=[SimpleNamespace(index=i, embedding=[0.1, 0.2])
                                         for i in range(len(kwargs["input"]))],
                                   usage=SimpleNamespace(prompt_tokens=10, total_tokens=10))
        client = SimpleNamespace(get_or_create_collection=lambda **kwargs: collection)
        modules = {"chromadb": SimpleNamespace(CloudClient=lambda **kwargs: client),
                   "openai": SimpleNamespace(OpenAI=lambda **kwargs: SimpleNamespace(
                       embeddings=SimpleNamespace(create=embed)))}
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {"CHROMA_API_KEY": "fixture", "OPENAI_API_KEY": "fixture"}):
            count = vault.build_chroma_index(FIXTURE, vault.DEFAULT_EMBEDDING_MODEL)
        self.assertEqual(len(stored), count)


if __name__ == "__main__":
    unittest.main()
