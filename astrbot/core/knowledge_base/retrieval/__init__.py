"""检索模块"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import RetrievalManager, RetrievalResult
    from .rank_fusion import FusedResult, RankFusion
    from .sparse_retriever import SparseResult, SparseRetriever

__all__ = [
    "FusedResult",
    "RankFusion",
    "RetrievalManager",
    "RetrievalResult",
    "SparseResult",
    "SparseRetriever",
]


def __getattr__(name: str):
    if name in {"RetrievalManager", "RetrievalResult"}:
        from .manager import RetrievalManager, RetrievalResult

        return {
            "RetrievalManager": RetrievalManager,
            "RetrievalResult": RetrievalResult,
        }[name]

    if name in {"FusedResult", "RankFusion"}:
        from .rank_fusion import FusedResult, RankFusion

        return {
            "FusedResult": FusedResult,
            "RankFusion": RankFusion,
        }[name]

    if name in {"SparseResult", "SparseRetriever"}:
        from .sparse_retriever import SparseResult, SparseRetriever

        return {
            "SparseResult": SparseResult,
            "SparseRetriever": SparseRetriever,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
