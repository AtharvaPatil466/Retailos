import json
from typing import Any, Optional

import redis.asyncio as redis


# Maps event types to relevant memory key patterns
EVENT_MEMORY_MAP = {
    "low_stock": ["product:{sku}:restock_history", "supplier:*:history", "orchestrator:daily_summary"],
    "supplier_reply": ["supplier:{supplier_id}:history", "product:{sku}:restock_history"],
    "procurement_needed": ["supplier:*:history", "orchestrator:daily_summary"],
    "customer_offer": ["customer:*:purchases", "customer:*:last_offer"],
    "daily_analytics": ["orchestrator:daily_summary", "supplier:*:history", "product:*:restock_history"],
    "shelf_optimization": ["shelf:*:placement_history", "orchestrator:daily_summary"],
    "shelf_placement_approved": ["shelf:*:placement_history"],
}


class Memory:
    """Redis-backed persistent memory for RetailOS.

    Structured key-value storage organized by domain.
    Not vector search — deliberate key-value with domain-specific key patterns.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.client: Optional[redis.Redis] = None
        self._fallback: dict[str, str] = {}

    async def init(self, require_redis: bool = False) -> None:
        try:
            self.client = redis.from_url(self.redis_url, decode_responses=True)
            await self.client.ping()
        except Exception:
            self.client = None
            if require_redis:
                raise RuntimeError(
                    "Redis is required in production but unavailable at "
                    f"{self.redis_url}. Set REDIS_URL to a valid Redis instance. "
                    "Multi-instance deployments without Redis will have "
                    "inconsistent approvals, memory, and task queue state."
                )

    async def get(self, key: str) -> Any:
        if self.client:
            try:
                val = await self.client.get(key)
                if val is None:
                    return None
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return val
            except Exception:
                pass
        val = self._fallback.get(key)
        if val is None:
            return None
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        serialized = json.dumps(value) if not isinstance(value, str) else value
        if self.client:
            try:
                if ttl:
                    await self.client.setex(key, ttl, serialized)
                else:
                    await self.client.set(key, serialized)
                return
            except Exception:
                pass
        self._fallback[key] = serialized

    async def delete(self, key: str) -> None:
        if self.client:
            try:
                await self.client.delete(key)
                return
            except Exception:
                pass
        self._fallback.pop(key, None)

    async def get_relevant(self, event_type: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fetch all memory keys relevant to a given event type.

        Resolves placeholders like {sku} and {supplier_id} from context.
        """
        patterns = EVENT_MEMORY_MAP.get(event_type, [])
        context = context or {}
        result = {}

        for pattern in patterns:
            # Resolve placeholders
            resolved = pattern
            for placeholder_key, placeholder_val in context.items():
                resolved = resolved.replace(f"{{{placeholder_key}}}", str(placeholder_val))

            if "*" in resolved:
                # Wildcard — scan for matching keys
                keys = await self._scan_keys(resolved)
                for key in keys[:20]:  # Cap at 20 to keep prompts focused
                    val = await self.get(key)
                    if val is not None:
                        result[key] = val
            else:
                val = await self.get(resolved)
                if val is not None:
                    result[resolved] = val

        return result

    async def _scan_keys(self, pattern: str) -> list[str]:
        if self.client:
            try:
                keys = []
                async for key in self.client.scan_iter(match=pattern, count=100):
                    keys.append(key)
                    if len(keys) >= 50:
                        break
                return keys
            except Exception:
                pass
        # Fallback: match against in-memory keys
        import fnmatch
        return [k for k in self._fallback.keys() if fnmatch.fnmatch(k, pattern)]

    async def get_all_with_prefix(self, prefix: str) -> dict[str, Any]:
        return await self.get_relevant("", {}) if not prefix else {
            k: await self.get(k) for k in await self._scan_keys(f"{prefix}*")
        }

    async def close(self) -> None:
        if self.client:
            await self.client.close()
