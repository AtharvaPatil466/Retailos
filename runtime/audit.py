import asyncio
import hashlib
import json
import time
import uuid
from typing import Any, Optional

import asyncpg


def _compute_hash(entry: dict, previous_hash: str = "") -> str:
    """Compute SHA-256 hash of an audit entry chained to the previous entry.

    This creates a blockchain-like chain where tampering with any entry
    invalidates all subsequent hashes, making modifications detectable.
    """
    # Canonical representation: sorted keys, deterministic JSON
    canonical = json.dumps({
        "id": entry.get("id", ""),
        "timestamp": entry.get("timestamp", 0),
        "skill": entry.get("skill", ""),
        "event_type": entry.get("event_type", ""),
        "decision": entry.get("decision", ""),
        "reasoning": entry.get("reasoning", ""),
        "outcome": entry.get("outcome", ""),
        "status": entry.get("status", ""),
        "previous_hash": previous_hash,
    }, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


class AuditLogger:
    """Append-only, tamper-proof audit trail.

    Every action the system takes is logged with full reasoning.
    Nothing is ever deleted or modified.

    Tamper-proofing:
    - Each entry contains a SHA-256 hash chained to the previous entry
    - Modifying any entry breaks the hash chain, making tampering detectable
    - Verification endpoint checks the entire chain integrity
    """

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
        self._fallback_logs: list[dict] = []
        self._last_hash: str = ""  # Hash of the most recent entry
        self.on_log: Optional[callable] = None

    async def init(self) -> None:
        try:
            self.pool = await asyncpg.create_pool(self.database_url, min_size=2, max_size=10)
            await self.pool.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    timestamp DOUBLE PRECISION NOT NULL,
                    skill TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reasoning TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata JSONB DEFAULT '{}',
                    hash TEXT DEFAULT '',
                    previous_hash TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_skill ON audit_log(skill);
                CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_log(event_type);
            """)
            # Add hash columns if upgrading from older schema
            try:
                await self.pool.execute("ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS hash TEXT DEFAULT ''")
                await self.pool.execute("ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS previous_hash TEXT DEFAULT ''")
            except Exception:
                pass  # Columns already exist
            # Restore the hash chain head from the most recent entry
            row = await self.pool.fetchrow(
                "SELECT hash FROM audit_log ORDER BY timestamp DESC LIMIT 1"
            )
            if row and row["hash"]:
                self._last_hash = row["hash"]
        except Exception:
            # Fall back to in-memory logging if PostgreSQL is unavailable
            self.pool = None

    async def log(
        self,
        skill: str,
        event_type: str,
        decision: str,
        reasoning: str,
        outcome: str,
        status: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "skill": skill,
            "event_type": event_type,
            "decision": decision,
            "reasoning": reasoning,
            "outcome": outcome,
            "status": status,
            "metadata": metadata or {},
        }

        # Compute tamper-proof hash chain
        entry["previous_hash"] = self._last_hash
        entry["hash"] = _compute_hash(entry, self._last_hash)
        self._last_hash = entry["hash"]

        if self.pool:
            try:
                await self.pool.execute(
                    """
                    INSERT INTO audit_log (id, timestamp, skill, event_type, decision, reasoning, outcome, status, metadata, hash, previous_hash)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    """,
                    entry["id"],
                    entry["timestamp"],
                    skill,
                    event_type,
                    decision,
                    reasoning,
                    outcome,
                    status,
                    json.dumps(metadata or {}),
                    entry["hash"],
                    entry["previous_hash"],
                )
            except Exception:
                self._fallback_logs.append(entry)
        else:
            self._fallback_logs.append(entry)

        if self.on_log:
            try:
                if asyncio.iscoroutinefunction(self.on_log):
                    asyncio.create_task(self.on_log(entry))
                else:
                    self.on_log(entry)
            except Exception:
                pass

        return entry

    async def get_logs(
        self,
        skill: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if self.pool:
            query = "SELECT * FROM audit_log WHERE 1=1"
            params = []
            idx = 1

            if skill:
                query += f" AND skill = ${idx}"
                params.append(skill)
                idx += 1
            if event_type:
                query += f" AND event_type = ${idx}"
                params.append(event_type)
                idx += 1

            query += f" ORDER BY timestamp DESC LIMIT ${idx} OFFSET ${idx + 1}"
            idx += 2
            params.extend([limit, offset])

            rows = await self.pool.fetch(query, *params)
            return [
                {
                    "id": r["id"],
                    "timestamp": r["timestamp"],
                    "skill": r["skill"],
                    "event_type": r["event_type"],
                    "decision": r["decision"],
                    "reasoning": r["reasoning"],
                    "outcome": r["outcome"],
                    "status": r["status"],
                    "metadata": json.loads(r["metadata"]) if isinstance(r["metadata"], str) else r["metadata"],
                }
                for r in rows
            ]
        else:
            logs = self._fallback_logs[:]
            if skill:
                logs = [entry for entry in logs if entry["skill"] == skill]
            if event_type:
                logs = [entry for entry in logs if entry["event_type"] == event_type]
            logs.sort(key=lambda x: x["timestamp"], reverse=True)
            return logs[offset : offset + limit]

    async def get_log_count(self) -> int:
        if self.pool:
            row = await self.pool.fetchrow("SELECT COUNT(*) as cnt FROM audit_log")
            return row["cnt"]
        return len(self._fallback_logs)

    async def verify_chain(self) -> dict[str, Any]:
        """Verify the integrity of the entire audit log hash chain.

        Returns verification result with any detected tampering.
        """
        logs = await self.get_logs(limit=10000)
        logs.reverse()  # Oldest first for chain verification

        if not logs:
            return {"status": "ok", "entries_checked": 0, "message": "No entries to verify"}

        errors = []
        previous_hash = ""

        for i, entry in enumerate(logs):
            expected_hash = _compute_hash(entry, previous_hash)

            if "hash" in entry and entry["hash"] != expected_hash:
                errors.append({
                    "entry_index": i,
                    "entry_id": entry.get("id", ""),
                    "timestamp": entry.get("timestamp", 0),
                    "expected_hash": expected_hash[:16] + "...",
                    "actual_hash": entry["hash"][:16] + "...",
                    "issue": "Hash mismatch — entry may have been tampered with",
                })

            if "previous_hash" in entry and entry["previous_hash"] != previous_hash:
                errors.append({
                    "entry_index": i,
                    "entry_id": entry.get("id", ""),
                    "issue": "Chain link broken — previous hash mismatch",
                })

            previous_hash = entry.get("hash", expected_hash)

        if errors:
            return {
                "status": "tampered",
                "entries_checked": len(logs),
                "errors": errors,
                "message": f"INTEGRITY VIOLATION: {len(errors)} entries may have been tampered with",
            }

        return {
            "status": "ok",
            "entries_checked": len(logs),
            "chain_head_hash": self._last_hash[:16] + "..." if self._last_hash else "",
            "message": "All entries verified — hash chain is intact",
        }

    async def verify_entry(self, entry_id: str) -> dict[str, Any]:
        """Verify a single audit entry's integrity."""
        logs = await self.get_logs(limit=10000)
        logs.reverse()

        target = None
        prev_entry = None
        for i, entry in enumerate(logs):
            if entry.get("id") == entry_id:
                target = entry
                prev_entry = logs[i - 1] if i > 0 else None
                break

        if not target:
            return {"status": "not_found", "entry_id": entry_id}

        prev_hash = prev_entry.get("hash", "") if prev_entry else ""
        expected = _compute_hash(target, prev_hash)
        actual = target.get("hash", "")

        return {
            "entry_id": entry_id,
            "status": "ok" if actual == expected else "tampered",
            "hash_match": actual == expected,
            "timestamp": target.get("timestamp", 0),
        }

    def get_chain_info(self) -> dict[str, Any]:
        """Get current hash chain status."""
        return {
            "chain_length": len(self._fallback_logs),
            "chain_head_hash": self._last_hash[:16] + "..." if self._last_hash else "",
            "algorithm": "SHA-256",
            "chaining": "Each entry hash includes previous entry hash",
        }

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
