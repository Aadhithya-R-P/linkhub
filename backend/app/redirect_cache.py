"""Disposable redirect data. PostgreSQL remains the source of truth."""
from functools import lru_cache
from datetime import datetime
import logging

from pydantic import AwareDatetime, BaseModel, ConfigDict, HttpUrl, ValidationError
from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry

from app.config import Settings

logger = logging.getLogger(__name__)


class CachedRedirect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination_url: HttpUrl
    expires_at: AwareDatetime | None


class RedirectCache:
    def __init__(self, client: Redis | None, ttl_seconds: int = 30,
                 prefix: str = "linkhub:redirect:v1:"):
        self.client = client
        self.ttl_seconds = ttl_seconds
        self.prefix = prefix

    def get(self, link_id: int) -> CachedRedirect | None:
        if self.client is None:
            return None
        try:
            raw = self.client.get(f"{self.prefix}{link_id}")
            return CachedRedirect.model_validate_json(raw) if raw is not None else None
        except (ValidationError, UnicodeError):
            logger.warning("Invalid redirect cache entry; using PostgreSQL.")
            return None
        except RedisError:
            logger.warning("Redirect cache read failed; using PostgreSQL.")
            return None

    def put(self, link_id: int, destination: str, expires_at: datetime | None) -> None:
        if self.client is None:
            return
        entry = CachedRedirect(destination_url=destination, expires_at=expires_at)
        try:
            self.client.set(f"{self.prefix}{link_id}", entry.model_dump_json(), ex=self.ttl_seconds)
        except RedisError:
            logger.warning("Redirect cache write failed; continuing without caching.")

    def invalidate(self, link_id: int) -> None:
        if self.client is None:
            return
        try:
            self.client.delete(f"{self.prefix}{link_id}")
        except RedisError:
            logger.warning("Redirect cache invalidation failed; stale data may remain until expiry.")


@lru_cache(maxsize=1)
def get_redirect_cache() -> RedirectCache:
    settings = Settings()
    client = None
    if settings.redirect_cache_enabled:
        client = Redis.from_url(
            settings.redis_url.get_secret_value(),
            socket_connect_timeout=settings.redis_timeout_seconds,
            socket_timeout=settings.redis_timeout_seconds,
            retry=Retry(NoBackoff(), 0),
        )
    return RedirectCache(client, settings.redirect_cache_ttl_seconds)
