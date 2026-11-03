import logging
import os
from uuid import uuid4

from google.protobuf.message import DecodeError
from redis.asyncio import Redis
from redis.asyncio.sentinel import Sentinel
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class FlightCache:
    def __init__(self, client=None, ttl_seconds=None):
        self.ttl = int(
            ttl_seconds
            if ttl_seconds is not None
            else os.getenv("CACHE_TTL_SECONDS", "300")
        )
        if not 300 <= self.ttl <= 600:
            raise ValueError("CACHE_TTL_SECONDS must be between 300 and 600")
        self.sentinel = None
        self.client = client
        if self.client is None:
            self.client = self._connect()
        self._generation = uuid4().hex

    def _connect(self):
        options = dict(socket_connect_timeout=0.3, socket_timeout=0.3)
        addresses = os.getenv("REDIS_SENTINELS")
        if not addresses:
            return Redis.from_url(
                os.getenv("REDIS_URL", "redis://localhost:6379/0"),
                **options,
            )
        endpoints = []
        for address in addresses.split(","):
            host, separator, port = address.strip().rpartition(":")
            if (
                not separator
                or not host
                or not port.isdecimal()
                or not 0 < int(port) < 65536
            ):
                raise ValueError(
                    "REDIS_SENTINELS must contain comma-separated host:port entries"
                )
            endpoints.append((host, int(port)))
        self.sentinel = Sentinel(endpoints, sentinel_kwargs=options, **options)
        return self.sentinel.master_for(os.getenv("REDIS_MASTER_NAME", "flight-cache"))

    def key(self, suffix):
        return f"flight-service:{self._generation}:{suffix}"

    async def check(self):
        try:
            await self.client.ping()
            logger.info("cache_connected")
        except RedisError:
            logger.warning("cache_unavailable operation=ping")

    async def get(self, key, message_type):
        try:
            value = await self.client.get(key)
            if value is not None:
                result = message_type.FromString(value)
                logger.info("cache_hit key=%s", key)
                return result
        except (RedisError, DecodeError):
            logger.warning("cache_read_failed key=%s", key)
        logger.info("cache_miss key=%s", key)
        return None

    async def put(self, key, message):
        try:
            await self.client.set(key, message.SerializeToString(), ex=self.ttl)
        except RedisError:
            logger.warning("cache_write_failed key=%s", key)

    def invalidate(self):
        self._generation = uuid4().hex
        logger.info("cache_invalidated")

    async def close(self):
        await self.client.aclose()
        if self.sentinel is not None:
            for client in self.sentinel.sentinels:
                await client.aclose()
