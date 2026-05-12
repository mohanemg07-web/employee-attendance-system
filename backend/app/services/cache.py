"""
Redis caching service for dashboard endpoints.

Provides functionality to get, set, and invalidate cache data.
Includes a circuit breaker to avoid blocking requests when Redis is down.
"""
import json
import logging
import time
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

# Try to import redis, but don't crash if it's missing (though it should be installed)
try:
    import redis.asyncio as redis
except ImportError:
    redis = None

from app.config import get_settings
from app.services.hierarchy import get_direct_managers

logger = logging.getLogger(__name__)
settings = get_settings()

_redis_client = None

# ── Circuit Breaker State ───────────────────────────────
# After _CB_THRESHOLD consecutive failures, skip Redis for _CB_COOLDOWN seconds
# to avoid blocking every request with connection timeouts.
_CB_THRESHOLD = 3
_CB_COOLDOWN = 60  # seconds
_cb_failures = 0
_cb_open_until = 0.0


def _cb_is_open() -> bool:
    """Return True if the circuit breaker is open (Redis should be skipped)."""
    global _cb_failures, _cb_open_until
    if _cb_open_until > 0 and time.time() < _cb_open_until:
        return True
    if _cb_open_until > 0 and time.time() >= _cb_open_until:
        # Cooldown expired — half-open, allow one probe
        _cb_open_until = 0.0
        _cb_failures = 0
    return False


def _cb_record_failure():
    """Record a Redis failure. Opens the circuit after threshold is hit."""
    global _cb_failures, _cb_open_until
    _cb_failures += 1
    if _cb_failures >= _CB_THRESHOLD:
        _cb_open_until = time.time() + _CB_COOLDOWN
        logger.warning(
            "Redis circuit breaker OPEN — skipping cache for %ds after %d failures",
            _CB_COOLDOWN, _cb_failures,
        )


def _cb_record_success():
    """Record a Redis success. Resets the circuit breaker."""
    global _cb_failures, _cb_open_until
    _cb_failures = 0
    _cb_open_until = 0.0


def get_redis():
    """Get or initialize the Redis client singleton (with fast fail timeout)."""
    global _redis_client
    if redis is None:
        return None
    if _redis_client is None and settings.REDIS_URL:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=0.3,
            socket_connect_timeout=0.3,
        )
    return _redis_client


async def get_cache(key: str) -> Optional[Any]:
    """Retrieve and deserialize data from Redis."""
    if _cb_is_open():
        return None
    client = get_redis()
    if not client:
        return None
    try:
        data = await client.get(key)
        if data:
            _cb_record_success()
            return json.loads(data)
        _cb_record_success()
    except Exception as e:
        _cb_record_failure()
        logger.debug("Redis get error for %s: %s", key, e)
    return None


async def set_cache(key: str, data: Any, ttl_seconds: int = 300) -> bool:
    """Serialize and store data in Redis with a TTL."""
    if _cb_is_open():
        return False
    client = get_redis()
    if not client:
        return False
    try:
        # Use json.dumps to serialize dictionaries and lists
        await client.setex(key, ttl_seconds, json.dumps(data))
        _cb_record_success()
        return True
    except Exception as e:
        _cb_record_failure()
        logger.debug("Redis set error for %s: %s", key, e)
        return False


async def invalidate_pattern(pattern: str) -> int:
    """Delete all keys matching a specific pattern."""
    if _cb_is_open():
        return 0
    client = get_redis()
    if not client:
        return 0
    try:
        keys = await client.keys(pattern)
        if keys:
            await client.delete(*keys)
            _cb_record_success()
            return len(keys)
        _cb_record_success()
    except Exception as e:
        _cb_record_failure()
        logger.debug("Redis invalidate error for pattern %s: %s", pattern, e)
    return 0


async def invalidate_dashboard_caches(db: AsyncSession, employee_ids: List[int]) -> None:
    """
    Invalidate all related dashboard caches for a list of employees.
    This invalidates the employees' own /me/dashboard caches, and
    their managers' /team/dashboard caches.
    """
    if _cb_is_open():
        return
    client = get_redis()
    if not client or not employee_ids:
        return

    try:
        # 1. Invalidate employees' personal dashboards
        for emp_id in employee_ids:
            await invalidate_pattern(f"dashboard:me:{emp_id}:*")

        # 2. Find their managers and invalidate team dashboards
        manager_ids = await get_direct_managers(db, employee_ids)
        for mgr_id in manager_ids:
            await invalidate_pattern(f"dashboard:team:{mgr_id}:*")
            
        logger.info(f"Invalidated caches for {len(employee_ids)} employees and {len(manager_ids)} managers.")
    except Exception as e:
        logger.error(f"Error invalidating dashboard caches: {e}")
