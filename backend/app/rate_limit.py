"""Shared fixed-window counters. Redis time/expiry is authoritative across workers."""
from functools import lru_cache
import hashlib
import hmac
import logging
import math

from fastapi import Depends, HTTPException
from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry

from app.config import Settings
from app.dependencies import get_current_user
from app.models import User

logger = logging.getLogger(__name__)

# One atomic operation: no INCR/EXPIRE race and blocked attempts never extend TTL.
# Windows start at the first request. Cap the counter once the limit is reached.
COUNTER_SCRIPT = """
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
local ttl = redis.call('PTTL', KEYS[1])
if ttl <= 0 then
    redis.call('SET', KEYS[1], 1, 'PX', ARGV[2])
    return {1, tonumber(ARGV[2])}
end
if count >= tonumber(ARGV[1]) then
    return {0, ttl}
end
redis.call('INCR', KEYS[1])
return {1, ttl}
"""


class RateLimiter:
    def __init__(self, client: Redis, key_secret: str, prefix="linkhub:limit:v1:"):
        self.client = client
        self.key_secret = key_secret.encode()
        self.prefix = prefix

    def check(self, scope: str, identity: str, limit: int, window_seconds: int) -> int:
        """Return zero when allowed, otherwise seconds until another attempt."""
        digest = hmac.new(self.key_secret, identity.encode(), hashlib.sha256).hexdigest()
        # Include policy so changing limits does not inherit an incompatible window.
        key = f"{self.prefix}{scope}:{limit}:{window_seconds}:{digest}"
        allowed, ttl_ms = self.client.eval(COUNTER_SCRIPT, 1, key, limit, window_seconds * 1000)
        return 0 if allowed else max(1, math.ceil(ttl_ms / 1000))


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    settings = Settings()
    client = Redis.from_url(
        settings.redis_url.get_secret_value(),
        socket_connect_timeout=settings.redis_timeout_seconds,
        socket_timeout=settings.redis_timeout_seconds,
        retry=Retry(NoBackoff(), 0),
    )
    return RateLimiter(client, settings.jwt_secret.get_secret_value())


def enforce_mutation_limit(user_id: int, settings: Settings) -> None:
    if not settings.rate_limit_enabled:
        return
    try:
        retry_after = get_rate_limiter().check(
            "mutation", f"user:{user_id}", settings.rate_limit_mutation_requests,
            settings.rate_limit_mutation_window_seconds,
        )
    except RedisError:
        # Never log exception values, IPs, credentials or Redis URLs.
        logger.warning("Link rate limiter unavailable; allowing the request.")
        return
    if retry_after:
        raise HTTPException(429, "Too many requests. Please try again later.",
                            headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"})


def limit_link_mutation(user: User = Depends(get_current_user)) -> None:
    enforce_mutation_limit(user.id, Settings())
