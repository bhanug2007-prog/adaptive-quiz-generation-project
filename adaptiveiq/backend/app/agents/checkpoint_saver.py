"""SQLAlchemy-backed LangGraph checkpoint saver for Stage 2 Personalized Learning Plans.

Works identically on local SQLite and PostgreSQL deployments using AdaptiveIQ's
configured Database engine and Alembic-managed tables (lg_checkpoints,
lg_checkpoint_blobs, lg_checkpoint_writes), without requiring Redis or extra services.

Non-serializable runtime objects (Session, Settings, Request, datetime now, API keys)
MUST stay in config["configurable"] and NEVER inside graph state.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Sequence
import random
import threading
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    SerializerProtocol,
    get_checkpoint_id,
    get_checkpoint_metadata,
    writes_sort_key,
)
from sqlalchemy import delete, select
from sqlalchemy.dialects import postgresql, sqlite

from app.core.db import Database
from app.models.base import utcnow
from app.models.learning_agent import (
    LangGraphCheckpoint,
    LangGraphCheckpointBlob,
    LangGraphCheckpointWrite,
)


def _upsert_stmt(dialect_name: str, table, values: dict, conflict_cols: list[str], update_cols: list[str] | None = None):
    """Builds a portable atomic upsert (or insert-ignore) for PostgreSQL and SQLite."""
    if dialect_name == "postgresql":
        stmt = postgresql.insert(table).values(**values)
        if update_cols:
            return stmt.on_conflict_do_update(
                index_elements=conflict_cols,
                set_={c: stmt.excluded[c] for c in update_cols},
            )
        return stmt.on_conflict_do_nothing(index_elements=conflict_cols)

    if dialect_name == "sqlite":
        stmt = sqlite.insert(table).values(**values)
        if update_cols:
            return stmt.on_conflict_do_update(
                index_elements=conflict_cols,
                set_={c: stmt.excluded[c] for c in update_cols},
            )
        return stmt.on_conflict_do_nothing(index_elements=conflict_cols)

    return None


class SQLAlchemyCheckpointSaver(BaseCheckpointSaver[str]):
    """Durable transaction-safe LangGraph BaseCheckpointSaver backed by SQLAlchemy.

    Uses its own short Database sessions so LangGraph interrupt and resume checkpoints
    persist atomically even if an HTTP request session rolls back on a later validation
    error, and never holds a concurrent write lock while application nodes commit.
    """

    def __init__(
        self,
        database: Database,
        *,
        serde: SerializerProtocol | None = None,
    ) -> None:
        super().__init__(serde=serde)
        self.dbm = database
        self._dialect = database.engine.dialect.name
        self._lock = threading.RLock()

    def _load_blobs(
        self,
        db,
        thread_id: str,
        checkpoint_ns: str,
        versions: ChannelVersions,
    ) -> dict[str, Any]:
        if not versions:
            return {}
        target = {k: str(v) for k, v in versions.items()}
        channels = list(target.keys())
        ver_strs = list(set(target.values()))
        rows = db.scalars(
            select(LangGraphCheckpointBlob).where(
                LangGraphCheckpointBlob.thread_id == thread_id,
                LangGraphCheckpointBlob.checkpoint_ns == checkpoint_ns,
                LangGraphCheckpointBlob.channel.in_(channels),
                LangGraphCheckpointBlob.version.in_(ver_strs),
            )
        )
        result: dict[str, Any] = {}
        for row in rows:
            if target.get(row.channel) != row.version:
                continue
            if row.type == "empty":
                continue
            result[row.channel] = self.serde.loads_typed((row.type, row.blob or b""))
        return result

    def _ordered_writes(
        self,
        db,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
    ) -> list[tuple[str, str, tuple[str, bytes]]]:
        rows = list(
            db.scalars(
                select(LangGraphCheckpointWrite).where(
                    LangGraphCheckpointWrite.thread_id == thread_id,
                    LangGraphCheckpointWrite.checkpoint_ns == checkpoint_ns,
                    LangGraphCheckpointWrite.checkpoint_id == checkpoint_id,
                )
            )
        )
        rows.sort(key=lambda r: writes_sort_key(r.task_path or "", r.task_id, r.idx))
        out: list[tuple[str, str, tuple[str, bytes]]] = []
        for r in rows:
            val = self.serde.loads_typed((r.type or "json", r.blob))
            out.append((r.task_id, r.channel, val))
        return out

    def _row_to_tuple(
        self,
        db,
        row: LangGraphCheckpoint,
        config: RunnableConfig | None = None,
    ) -> CheckpointTuple:
        checkpoint_data: Checkpoint = self.serde.loads_typed((row.type or "json", row.checkpoint))
        metadata: CheckpointMetadata = self.serde.loads_typed((row.metadata_type or "json", row.metadata_blob))
        pending_writes = self._ordered_writes(db, row.thread_id, row.checkpoint_ns, row.checkpoint_id)
        eff_config: RunnableConfig = config or {
            "configurable": {
                "thread_id": row.thread_id,
                "checkpoint_ns": row.checkpoint_ns,
                "checkpoint_id": row.checkpoint_id,
            }
        }
        parent_cfg: RunnableConfig | None = (
            {
                "configurable": {
                    "thread_id": row.thread_id,
                    "checkpoint_ns": row.checkpoint_ns,
                    "checkpoint_id": row.parent_checkpoint_id,
                }
            }
            if row.parent_checkpoint_id
            else None
        )
        return CheckpointTuple(
            config=eff_config,
            checkpoint={
                **checkpoint_data,
                "channel_values": self._load_blobs(
                    db,
                    row.thread_id,
                    row.checkpoint_ns,
                    checkpoint_data.get("channel_versions", {}),
                ),
            },
            metadata=metadata,
            parent_config=parent_cfg,
            pending_writes=pending_writes,
        )

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = get_checkpoint_id(config)
        with self._lock, self.dbm.session() as db:
            if checkpoint_id:
                row = db.scalar(
                    select(LangGraphCheckpoint).where(
                        LangGraphCheckpoint.thread_id == thread_id,
                        LangGraphCheckpoint.checkpoint_ns == checkpoint_ns,
                        LangGraphCheckpoint.checkpoint_id == str(checkpoint_id),
                    )
                )
                return self._row_to_tuple(db, row, config=config) if row else None

            row = db.scalar(
                select(LangGraphCheckpoint)
                .where(
                    LangGraphCheckpoint.thread_id == thread_id,
                    LangGraphCheckpoint.checkpoint_ns == checkpoint_ns,
                )
                .order_by(LangGraphCheckpoint.checkpoint_id.desc())
                .limit(1)
            )
            return self._row_to_tuple(db, row) if row else None

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        with self._lock, self.dbm.session() as db:
            stmt = select(LangGraphCheckpoint)
            if config is not None:
                cfg = config.get("configurable", {})
                if "thread_id" in cfg:
                    stmt = stmt.where(LangGraphCheckpoint.thread_id == str(cfg["thread_id"]))
                if "checkpoint_ns" in cfg and cfg["checkpoint_ns"] is not None:
                    stmt = stmt.where(LangGraphCheckpoint.checkpoint_ns == str(cfg["checkpoint_ns"]))
                if cp_id := get_checkpoint_id(config):
                    stmt = stmt.where(LangGraphCheckpoint.checkpoint_id == str(cp_id))
            if before is not None and (before_id := get_checkpoint_id(before)):
                stmt = stmt.where(LangGraphCheckpoint.checkpoint_id < str(before_id))

            stmt = stmt.order_by(LangGraphCheckpoint.checkpoint_id.desc())
            rows = list(db.scalars(stmt))

            emitted = 0
            for row in rows:
                metadata: CheckpointMetadata = self.serde.loads_typed((row.metadata_type or "json", row.metadata_blob))
                if filter and not all(metadata.get(k) == v for k, v in filter.items()):
                    continue
                if limit is not None and emitted >= limit:
                    break
                emitted += 1
                yield self._row_to_tuple(db, row)

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        c = checkpoint.copy()
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")
        values: dict[str, Any] = c.pop("channel_values", {})  # type: ignore[misc]

        cp_type, cp_bytes = self.serde.dumps_typed(c)
        meta_type, meta_bytes = self.serde.dumps_typed(get_checkpoint_metadata(config, metadata))

        with self._lock, self.dbm.session() as db:
            for k, v in new_versions.items():
                ver_str = str(v)
                if k in values:
                    b_type, b_bytes = self.serde.dumps_typed(values[k])
                else:
                    b_type, b_bytes = "empty", b""
                blob_vals = {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "channel": k,
                    "version": ver_str,
                    "type": b_type,
                    "blob": b_bytes,
                }
                stmt = _upsert_stmt(
                    self._dialect,
                    LangGraphCheckpointBlob.__table__,
                    blob_vals,
                    ["thread_id", "checkpoint_ns", "channel", "version"],
                    update_cols=None,
                )
                if stmt is not None:
                    db.execute(stmt)
                else:
                    existing = db.get(LangGraphCheckpointBlob, (thread_id, checkpoint_ns, k, ver_str))
                    if existing is None:
                        db.add(LangGraphCheckpointBlob(**blob_vals))

            cp_vals = {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": str(checkpoint["id"]),
                "parent_checkpoint_id": str(parent_checkpoint_id) if parent_checkpoint_id else None,
                "type": cp_type,
                "checkpoint": cp_bytes,
                "metadata_type": meta_type,
                "metadata_blob": meta_bytes,
                "created_at": utcnow(),
            }
            cp_stmt = _upsert_stmt(
                self._dialect,
                LangGraphCheckpoint.__table__,
                cp_vals,
                ["thread_id", "checkpoint_ns", "checkpoint_id"],
                update_cols=["parent_checkpoint_id", "type", "checkpoint", "metadata_type", "metadata_blob"],
            )
            if cp_stmt is not None:
                db.execute(cp_stmt)
            else:
                db.merge(LangGraphCheckpoint(**cp_vals))
            db.commit()

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": str(checkpoint["id"]),
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = str(config["configurable"]["checkpoint_id"])

        with self._lock, self.dbm.session() as db:
            for idx, (channel, value) in enumerate(writes):
                write_idx = WRITES_IDX_MAP.get(channel, idx)
                w_type, w_bytes = self.serde.dumps_typed(value)
                write_vals = {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                    "task_id": str(task_id),
                    "idx": int(write_idx),
                    "channel": str(channel),
                    "type": w_type,
                    "blob": w_bytes,
                    "task_path": str(task_path or ""),
                }
                update_cols = ["channel", "type", "blob", "task_path"] if write_idx < 0 else None
                stmt = _upsert_stmt(
                    self._dialect,
                    LangGraphCheckpointWrite.__table__,
                    write_vals,
                    ["thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx"],
                    update_cols=update_cols,
                )
                if stmt is not None:
                    db.execute(stmt)
                else:
                    existing = db.get(
                        LangGraphCheckpointWrite,
                        (thread_id, checkpoint_ns, checkpoint_id, str(task_id), int(write_idx)),
                    )
                    if existing is None or write_idx < 0:
                        db.merge(LangGraphCheckpointWrite(**write_vals))
            db.commit()

    def delete_thread(self, thread_id: str) -> None:
        tid = str(thread_id)
        with self._lock, self.dbm.session() as db:
            db.execute(delete(LangGraphCheckpointWrite).where(LangGraphCheckpointWrite.thread_id == tid))
            db.execute(delete(LangGraphCheckpointBlob).where(LangGraphCheckpointBlob.thread_id == tid))
            db.execute(delete(LangGraphCheckpoint).where(LangGraphCheckpoint.thread_id == tid))
            db.commit()

    def get_next_version(self, current: str | None, channel: None) -> str:
        if current is None:
            current_v = 0
        elif isinstance(current, int):
            current_v = current
        else:
            current_v = int(str(current).split(".")[0])
        next_v = current_v + 1
        next_h = random.random()
        return f"{next_v:032}.{next_h:016}"

    # Async wrappers matching InMemorySaver contract
    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self.get_tuple(config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        return self.put_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        return self.delete_thread(thread_id)
