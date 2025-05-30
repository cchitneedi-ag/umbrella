import unittest

import pytest
from redis.exceptions import TimeoutError

from shared.helpers.cache import (
    NO_VALUE,
    BaseBackend,
    OurOwnCache,
    RedisBackend,
    make_hash_sha256,
)


class RandomCounter:
    def __init__(self):
        self.value = 0

    def call_function(self):
        self.value += 1
        return self.value

    def call_function_args(self, base, head, something=None, danger=True):
        return base + head

    async def async_call_function(self):
        self.value += 2
        self.value *= 4
        return self.value

    async def async_call_function_args(self, base, head, something=None, danger=True):
        return base + head


class FakeBackend(BaseBackend):
    def __init__(self):
        self.all_keys = {}

    def get(self, key):
        possible_values = self.all_keys.get(key, {})
        for val in possible_values.values():
            return val
        return NO_VALUE

    def set(self, key, ttl, value):
        if key not in self.all_keys:
            self.all_keys[key] = {}
        self.all_keys[key][ttl] = value


class FakeRedis:
    def __init__(self):
        self.all_keys = {}

    def get(self, key):
        return self.all_keys.get(key)

    def setex(self, key, expire, value):
        self.all_keys[key] = value


class FakeRedisWithIssues:
    def get(self, key):
        raise TimeoutError()

    def setex(self, key, expire, value):
        raise TimeoutError()


class TestRedisBackend(unittest.TestCase):
    def test_simple_redis_call(self):
        redis_backend = RedisBackend(FakeRedis())
        assert redis_backend.get("normal_key") == NO_VALUE
        value_1 = list(set("ascdefgh"))
        redis_backend.set("normal_key", 120, {"value_1": value_1, "1": [1, 3]})
        assert redis_backend.get("normal_key") == {
            "value_1": value_1,
            "1": [1, 3],
        }

    def test_simple_redis_call_exception(self):
        redis_backend = RedisBackend(FakeRedisWithIssues())
        assert redis_backend.get("normal_key") == NO_VALUE
        redis_backend.set(
            "normal_key", 120, {"value_1": list(set("ascdefgh")), "1": [1, 3]}
        )
        assert redis_backend.get("normal_key") == NO_VALUE

    def test_simple_redis_call_not_json_serializable(self):
        redis_backend = RedisBackend(FakeRedis())

        unserializable = set("abcdefg")
        redis_backend.set("normal_key", 120, unserializable)
        assert redis_backend.get("normal_key") == NO_VALUE

    def test_simple_redis_call_dict_with_int_keys(self):
        redis_backend = RedisBackend(FakeRedis())

        d = {"abcde": {1: [1, 2, 3], 2: [4, 5, 6]}}
        redis_backend.set("normal_key", 120, d)
        assert redis_backend.get("normal_key") == NO_VALUE


class TestCache:
    def test_simple_caching_no_backend_no_params(self):
        cache = OurOwnCache()
        sample_function = RandomCounter().call_function
        cached_function = cache.cache_function()(sample_function)
        assert cached_function() == 1
        assert cached_function() == 2
        assert cached_function() == 3

    def test_simple_caching_no_backend_no_params_with_ttl(self):
        cache = OurOwnCache()
        sample_function = RandomCounter().call_function
        cached_function = cache.cache_function(ttl=300)(sample_function)
        assert cached_function() == 1
        assert cached_function() == 2
        assert cached_function() == 3

    @pytest.mark.asyncio
    async def test_simple_caching_no_backend_async_no_params(self):
        cache = OurOwnCache()
        sample_function = RandomCounter().async_call_function
        cached_function = cache.cache_function()(sample_function)
        assert (await cached_function()) == 8
        assert (await cached_function()) == 40
        assert (await cached_function()) == 168

    def test_simple_caching_fake_backend_no_params(self):
        cache = OurOwnCache()
        cache.configure(FakeBackend())
        sample_function = RandomCounter().call_function
        cached_function = cache.cache_function()(sample_function)
        assert cached_function() == 1
        assert cached_function() == 1
        assert cached_function() == 1

    def test_simple_caching_fake_backend_with_params(self):
        cache = OurOwnCache()
        cache.configure(FakeBackend())
        sample_function = RandomCounter().call_function_args
        cached_function = cache.cache_function()(sample_function)
        assert cached_function("base", "head", something="batata") == "basehead"
        assert cached_function("base", "head", something="else") == "basehead"
        assert cached_function("base", "head", something="else") == "basehead"
        # Changing the way we call the function
        assert cached_function("base", head="head", something="else") == "basehead"
        assert cached_function("base", head="head", something="else") == "basehead"

    @pytest.mark.asyncio
    async def test_simple_caching_fake_backend_async_no_params(self):
        cache = OurOwnCache()
        cache.configure(FakeBackend())
        sample_function = RandomCounter().async_call_function
        cached_function = cache.cache_function()(sample_function)
        assert (await cached_function()) == 8
        assert (await cached_function()) == 8
        assert (await cached_function()) == 8

    @pytest.mark.asyncio
    async def test_simple_caching_fake_backend_async_with_params(self):
        cache = OurOwnCache()
        cache.configure(FakeBackend())
        sample_function = RandomCounter().async_call_function_args
        cached_function = cache.cache_function()(sample_function)
        assert await cached_function("base", "head", something="batata") == "basehead"
        assert await cached_function("base", "head", something="else") == "basehead"
        assert await cached_function("base", "head", something="else") == "basehead"
        # Changing the way we call the function
        assert (
            await cached_function("base", head="head", something="else") == "basehead"
        )
        assert (
            await cached_function("base", head="head", something="else") == "basehead"
        )

    @pytest.mark.asyncio
    async def test_make_hash_sha256(self):
        assert make_hash_sha256(1) == "a4ayc/80/OGda4BO/1o/V0etpOqiLx1JwB5S3beHW0s="
        assert (
            make_hash_sha256("somestring")
            == "l5nfZJ7iQAll9QGKjGm4wPuSgUoikOMrdpOw/36GLyw="
        )
        this_set = {"1", "something", "True", "another_string_of_values"}
        assert (
            make_hash_sha256(this_set) == "siFp5vd4+aI5SxlURDMV3Z5Yfn5qnpSbCctIewE6m44="
        )
        this_set.add("ooops")
        assert (
            make_hash_sha256(this_set) == "aoU2Of3YNk0/iW1hqfSkXPbhIAzGMHCSCoxsiLI2b8U="
        )
