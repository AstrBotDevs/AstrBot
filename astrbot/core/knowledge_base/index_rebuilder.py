from __future__ import annotations

import numpy as np

from astrbot.core import logger
from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage
from astrbot.core.provider.provider import EmbeddingProvider

from .index_path import build_index_path


class IndexRebuilder:
    async def sync(
        self,
        kb_helper,
        new_provider_id: str,
        batch_size: int = 32,
        progress_callback=None,
    ) -> None:
        """Incrementally sync vector index for a new embedding provider."""
        provider = await kb_helper.get_embedding_provider_by_id(new_provider_id)
        if not isinstance(provider, EmbeddingProvider):
            raise ValueError(f"Provider {new_provider_id} is not an EmbeddingProvider")

        new_index_path = build_index_path(kb_helper.kb_dir, new_provider_id)
        storage = EmbeddingStorage(provider.get_dim(), str(new_index_path))

        doc_int_ids = set(await kb_helper.vec_db.document_storage.get_all_int_ids())
        index_int_ids = set(storage.get_all_ids())

        to_delete = list(index_int_ids - doc_int_ids)
        to_add = list(doc_int_ids - index_int_ids)

        docs: list[dict] = []
        if to_add:
            docs = await kb_helper.vec_db.document_storage.get_documents_by_int_ids(
                to_add
            )
            docs = [doc for doc in docs if isinstance(doc.get("text"), str)]
        total = len(to_delete) + len(docs)
        done = 0

        if progress_callback:
            await progress_callback("prepare", done, total)

        if to_delete:
            await storage.delete(to_delete)
            done += len(to_delete)
            if progress_callback:
                await progress_callback("deleting", done, total)

        if docs:
            for i in range(0, len(docs), batch_size):
                batch_docs = docs[i : i + batch_size]
                batch_texts = [doc["text"] for doc in batch_docs]
                batch_ids = [int(doc["id"]) for doc in batch_docs]
                vectors = await provider.get_embeddings(batch_texts)
                await storage.insert_batch(
                    vectors=np.array(vectors, dtype=np.float32),
                    ids=batch_ids,
                )
                done += len(batch_docs)
                if progress_callback:
                    await progress_callback("embedding", done, total)

        # Switch runtime vec db first, then persist active provider.
        try:
            await kb_helper.vec_db.switch_index(
                index_store_path=str(new_index_path),
                embedding_provider=provider,
                rerank_provider=await kb_helper.get_rp(),
            )
        except Exception:
            logger.exception(
                "Failed to switch index in runtime for kb=%s provider=%s",
                kb_helper.kb.kb_id,
                new_provider_id,
            )
            raise
        kb_helper.kb.active_index_provider_id = new_provider_id
        await kb_helper.persist_kb()
        logger.info(
            "KB index rebuild finished: kb=%s provider=%s docs=%s",
            kb_helper.kb.kb_id,
            new_provider_id,
            len(doc_int_ids),
        )
        if progress_callback:
            await progress_callback("finished", total, total)
