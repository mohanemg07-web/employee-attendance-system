"""
Redis-based rate limiting dependency.

Uses the circuit breaker from cache.py to skip Redis when it's unavailable.
"""
from fastapi import Request, HTTPException, status, Depends
import logging
import time

from app.services.cache import get_redis, _cb_is_open, _cb_record_failure, _cb_record_success
from app.utils.security import get_current_user
from app.models.employee import Employee

logger = logging.getLogger(__name__)

# Config
RATE_LIMIT = 60
RATE_WINDOW = 60  # seconds

async def rate_limiter(
    request: Request,
    current_user: Employee = Depends(get_current_user),
):
    """
    Dependency that enforces a rate limit per user using Redis.
    Respects the shared circuit breaker — skips Redis when it's down.
    """
    # Skip if circuit breaker is open (Redis is known to be down)
    if _cb_is_open():
        return current_user

    client = get_redis()
    if not client:
        # If Redis isn't available, we skip rate limiting
        return current_user

    key = f"rate_limit:{current_user.id}"
    
    try:
        # Simple token bucket using Redis INCR and EXPIRE
        current_count = await client.get(key)
        
        if current_count is not None and int(current_count) >= RATE_LIMIT:
            logger.warning(f"Rate limit exceeded for user {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Try again later."
            )
            
        pipe = client.pipeline()
        pipe.incr(key, 1)
        if current_count is None:
            pipe.expire(key, RATE_WINDOW)
        await pipe.execute()
        _cb_record_success()
        
    except HTTPException:
        raise
    except Exception as e:
        _cb_record_failure()
        logger.debug("Rate limiting unavailable for user %d: %s", current_user.id, e)
        # Fail open if Redis has issues so we don't block legitimate traffic
        pass

    return current_user

