import uuid
from datetime import datetime, timezone

import numpy as np
from sqlmodel import Field, MetaData, SQLModel

MEMORY_TYPE_IMPORTANCE = {"persona": 1.3, "fact": 1.0, "ephemeral": 0.8}


class BaseMemoryModel(SQLModel, table=False):
    metadata = MetaData()


class MemoryChunk(BaseMemoryModel, table=True):
    """A chunk of memory stored in the system."""

    __tablename__ = "memory_chunks"  # type: ignore

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    mem_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
        index=True,
    )
    fact: str = Field(nullable=False)
    """The factual content of the memory chunk."""
    owner_id: str = Field(max_length=255, nullable=False, index=True)
    """The identifier of the owner (user) of the memory chunk."""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    """The timestamp when the memory chunk was created."""
    last_retrieval_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    """The timestamp when the memory chunk was last retrieved."""
    retrieval_count: int = Field(default=1, nullable=False)
    """The number of times the memory chunk has been retrieved."""
    memory_type: str = Field(max_length=20, nullable=False, default="fact")
    """The type of memory (e.g., 'persona', 'fact', 'ephemeral')."""
    is_active: bool = Field(default=True, nullable=False)
    """Whether the memory chunk is active."""

    def compute_decay_score(self, current_time: datetime) -> float:
        """Compute the decay score of the memory chunk based on time and retrievals."""
        # Constants for the decay formula
        alpha = 0.5
        gamma = 0.1
        lambda_ = 0.05
        a = 0.1

        # Calculate delta_t in days
        delta_t = (current_time - self.last_retrieval_at).total_seconds() / 86400
        c = self.retrieval_count
        beta = 1 / (1 + a * c)
        decay_score = alpha * np.exp(-lambda_ * delta_t * beta) + (1 - alpha) * (
            1 - np.exp(-gamma * c)
        )
        return decay_score * MEMORY_TYPE_IMPORTANCE.get(self.memory_type, 1.0)
