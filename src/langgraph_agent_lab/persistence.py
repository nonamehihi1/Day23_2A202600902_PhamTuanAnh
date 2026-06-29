"""Checkpointer adapter."""

from __future__ import annotations

from typing import Any
import sqlite3

def build_checkpointer(kind: str = "memory", database_url: str | None = None) -> Any | None:
    """Return a LangGraph checkpointer."""
    if kind == "none":
        return None
    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    if kind == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError as exc:
            raise RuntimeError("Install: pip install langgraph-checkpoint-sqlite") from exc
        
        db_path = database_url or ":memory:"
        conn = sqlite3.connect(db_path, check_same_thread=False)
        return SqliteSaver(conn=conn)
        
    if kind == "postgres":
        raise NotImplementedError(
            "TODO(student): implement Postgres checkpointer (optional extension)"
        )
    raise ValueError(f"Unknown checkpointer kind: {kind}")
