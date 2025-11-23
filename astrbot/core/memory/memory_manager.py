import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from astrbot.core import logger
from astrbot.core.db.vec_db.faiss_impl import FaissVecDB
from astrbot.core.provider.provider import EmbeddingProvider
from astrbot.core.provider.provider import Provider as LLMProvider

from .entities import MemoryChunk
from .mem_db_sqlite import MemoryDatabase

MERGE_THRESHOLD = 0.85
"""Similarity threshold for merging memories"""
HEBB_THRESHOLD = 0.70
"""Similarity threshold for Hebbian learning reinforcement"""
MERGE_SYSTEM_PROMPT = """You are a memory consolidation assistant. Your task is to merge two related memory entries into a single, comprehensive memory.

Input format:
- Old memory: [existing memory content]
- New memory: [new memory content to be integrated]

Your output should be a single, concise memory that combines the essential information from both entries. Preserve specific details, update outdated information, and eliminate redundancy. Output only the merged memory content without any explanations or meta-commentary."""


class MemoryManager:
    """Manager for user long-term memory storage and retrieval"""

    def __init__(self, memory_root_dir: str = "data/astr_memory"):
        self.memory_root_dir = Path(memory_root_dir)
        self.memory_root_dir.mkdir(parents=True, exist_ok=True)

        self.mem_db: MemoryDatabase | None = None
        self.vec_db: FaissVecDB | None = None

        self._initialized = False

    async def initialize(
        self,
        embedding_provider: EmbeddingProvider,
        merge_llm_provider: LLMProvider,
    ):
        """Initialize memory database and vector database"""
        # Initialize MemoryDB
        db_path = self.memory_root_dir / "memory.db"
        self.mem_db = MemoryDatabase(db_path.as_posix())
        await self.mem_db.initialize()

        self.embedding_provider = embedding_provider
        self.merge_llm_provider = merge_llm_provider

        # Initialize VecDB
        doc_store_path = self.memory_root_dir / "doc.db"
        index_store_path = self.memory_root_dir / "index.faiss"
        self.vec_db = FaissVecDB(
            doc_store_path=doc_store_path.as_posix(),
            index_store_path=index_store_path.as_posix(),
            embedding_provider=self.embedding_provider,
        )
        await self.vec_db.initialize()

        logger.info("Memory manager initialized")
        self._initialized = True

    async def terminate(self):
        """Close all database connections"""
        if self.vec_db:
            await self.vec_db.close()
        if self.mem_db:
            await self.mem_db.close()

    async def add_memory(
        self,
        fact: str,
        owner_id: str,
        memory_type: str = "fact",
    ) -> MemoryChunk:
        """Add a new memory with similarity check and merge logic

        Implements the ADD MEMORY workflow from _README.md:
        1. Search for similar memories using VecDB
        2. If similarity >= merge_threshold, merge with existing memory
        3. Otherwise, create new memory
        4. Apply Hebbian learning to similar memories (similarity >= hebb_threshold)

        Args:
            fact: Memory content
            owner_id: User identifier
            memory_type: Memory type ('persona', 'fact', 'ephemeral')

        Returns:
            The created or updated MemoryChunk

        """
        if not self.vec_db or not self.mem_db:
            raise RuntimeError("Memory manager not initialized")

        current_time = datetime.now(timezone.utc)

        # Step 1: Search for similar memories
        similar_results = await self.vec_db.retrieve(
            query=fact,
            k=20,
            fetch_k=50,
            metadata_filters={"owner_id": owner_id},
        )

        # Step 2: Check if we should merge with existing memories (top 3 similar ones)
        merge_candidates = [
            r for r in similar_results[:3] if r.similarity >= MERGE_THRESHOLD
        ]

        if merge_candidates:
            # Get all candidate memories from database
            candidate_memories: list[tuple[str, MemoryChunk]] = []
            for candidate in merge_candidates:
                mem_id = json.loads(candidate.data["metadata"])["mem_id"]
                memory = await self.mem_db.get_memory_by_id(mem_id)
                if memory:
                    candidate_memories.append((mem_id, memory))

            if candidate_memories:
                # Use the most similar memory as the base
                base_mem_id, base_memory = candidate_memories[0]

                # Collect all facts to merge (existing candidates + new fact)
                all_facts = [mem.fact for _, mem in candidate_memories] + [fact]
                merged_fact = await self._merge_multiple_memories(all_facts)

                # Update the base memory
                base_memory.fact = merged_fact
                base_memory.last_retrieval_at = current_time
                base_memory.retrieval_count += 1
                updated_memory = await self.mem_db.update_memory(base_memory)

                # Update VecDB for base memory
                await self.vec_db.delete(base_mem_id)
                await self.vec_db.insert(
                    content=merged_fact,
                    metadata={
                        "mem_id": base_mem_id,
                        "owner_id": owner_id,
                        "memory_type": memory_type,
                    },
                    id=base_mem_id,
                )

                # Deactivate and remove other merged memories
                for mem_id, _ in candidate_memories[1:]:
                    await self.mem_db.deactivate_memory(mem_id)
                    await self.vec_db.delete(mem_id)

                logger.info(
                    f"Merged {len(candidate_memories)} memories into {base_mem_id} for user {owner_id}"
                )
                return updated_memory

        # Step 3: Create new memory
        mem_id = str(uuid.uuid4())
        new_memory = MemoryChunk(
            mem_id=mem_id,
            fact=fact,
            owner_id=owner_id,
            memory_type=memory_type,
            created_at=current_time,
            last_retrieval_at=current_time,
            retrieval_count=1,
            is_active=True,
        )

        # Insert into MemoryDB
        created_memory = await self.mem_db.insert_memory(new_memory)

        # Insert into VecDB
        await self.vec_db.insert(
            content=fact,
            metadata={
                "mem_id": mem_id,
                "owner_id": owner_id,
                "memory_type": memory_type,
            },
            id=mem_id,
        )

        # Step 4: Apply Hebbian learning to similar memories
        hebb_mem_ids = [
            json.loads(r.data["metadata"])["mem_id"]
            for r in similar_results
            if r.similarity >= HEBB_THRESHOLD
        ]
        if hebb_mem_ids:
            await self.mem_db.update_retrieval_stats(hebb_mem_ids, current_time)
            logger.debug(
                f"Applied Hebbian learning to {len(hebb_mem_ids)} memories for user {owner_id}",
            )

        logger.info(f"Created new memory {mem_id} for user {owner_id}")
        return created_memory

    async def query_memory(
        self,
        owner_id: str,
        top_k: int = 5,
    ) -> list[MemoryChunk]:
        """Query user's memories using static retrieval with decay score ranking

        Implements the QUERY MEMORY (STATIC) workflow from _README.md:
        1. Get all active memories for user from MemoryDB
        2. Compute decay_score for each memory
        3. Sort by decay_score and return top_k
        4. Update retrieval statistics for returned memories

        Args:
            owner_id: User identifier
            top_k: Number of memories to return

        Returns:
            List of top_k MemoryChunk sorted by decay score
        """
        if not self.mem_db:
            raise RuntimeError("Memory manager not initialized")

        current_time = datetime.now(timezone.utc)

        # Step 1: Get all active memories for user
        all_memories = await self.mem_db.get_active_memories(owner_id)

        if not all_memories:
            return []

        # Step 2-3: Compute decay scores and sort
        memories_with_scores = [
            (mem, mem.compute_decay_score(current_time)) for mem in all_memories
        ]
        memories_with_scores.sort(key=lambda x: x[1], reverse=True)

        # Get top_k memories
        top_memories = [mem for mem, _ in memories_with_scores[:top_k]]

        # Step 4: Update retrieval statistics
        mem_ids = [mem.mem_id for mem in top_memories]
        await self.mem_db.update_retrieval_stats(mem_ids, current_time)

        logger.debug(f"Retrieved {len(top_memories)} memories for user {owner_id}")
        return top_memories

    async def _merge_multiple_memories(self, facts: list[str]) -> str:
        """Merge multiple memory facts using LLM in one call

        Args:
            facts: List of memory facts to merge

        Returns:
            Merged memory content
        """
        if not self.merge_llm_provider:
            return " ".join(facts)

        if len(facts) == 1:
            return facts[0]

        try:
            # Format all facts as a numbered list
            facts_list = "\n".join(f"{i + 1}. {fact}" for i, fact in enumerate(facts))
            user_prompt = (
                f"Please merge the following {len(facts)} related memory entries "
                "into a single, comprehensive memory:"
                f"\n{facts_list}\n\nOutput only the merged memory content."
            )
            response = await self.merge_llm_provider.text_chat(
                prompt=user_prompt,
                system_prompt=MERGE_SYSTEM_PROMPT,
            )

            merged_content = response.completion_text.strip()
            return merged_content if merged_content else " ".join(facts)

        except Exception as e:
            logger.warning(f"Failed to merge memories with LLM: {e}, using fallback")
            return " ".join(facts)
