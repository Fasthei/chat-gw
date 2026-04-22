from __future__ import annotations

import time

import pytest
from jose import jwt

from app.auth.errors import InvalidTokenError
from app.auth.jwt_verify import JwtVerifier
from app.auth.roles import RoleResolver
from app.settings import Settings
from tests.conftest import DEV_SECRET, make_token


@pytest.fixture
def dev_settings() -> Settings:
    return Settings(jwt_dev_secret=DEV_SECRET, jwt_audience="chat-gw", jwt_issuer="")


class TestJwtVerifyDev:
    @pytest.mark.asyncio
    async def test_valid_token(self, dev_settings: Settings):
        v = JwtVerifier(dev_settings)
        claims = await v.verify(make_token(sub="alice", roles=["cloud_ops"]))
        assert claims["sub"] == "alice"
        assert claims["roles"] == ["cloud_ops"]

    @pytest.mark.asyncio
    async def test_expired(self, dev_settings: Settings):
        v = JwtVerifier(dev_settings)
        token = make_token(exp_offset=-120)
        with pytest.raises(InvalidTokenError):
            await v.verify(token)

    @pytest.mark.asyncio
    async def test_bad_signature(self, dev_settings: Settings):
        v = JwtVerifier(dev_settings)
        token = jwt.encode(
            {"sub": "x", "roles": [], "aud": "chat-gw", "exp": int(time.time()) + 60},
            "wrong-secret",
            algorithm="HS256",
        )
        with pytest.raises(InvalidTokenError):
            await v.verify(token)

    @pytest.mark.asyncio
    async def test_missing_token_rejected(self, dev_settings: Settings):
        v = JwtVerifier(dev_settings)
        with pytest.raises(InvalidTokenError):
            await v.verify("not.a.token")

    @pytest.mark.asyncio
    async def test_wrong_audience(self, dev_settings: Settings):
        v = JwtVerifier(dev_settings)
        token = make_token(audience="someone-else")
        with pytest.raises(InvalidTokenError):
            await v.verify(token)


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str):
        self.store[key] = value

    async def delete(self, key: str):
        self.store.pop(key, None)


class TestRoleResolver:
    @pytest.mark.asyncio
    async def test_primary_claim(self):
        redis = FakeRedis()
        rr = RoleResolver(roles_claim="roles", redis=redis, casdoor=None)
        roles = await rr.resolve("u1", {"roles": ["cloud_ops"]})
        assert roles == ["cloud_ops"]
        assert "roles:u1" in redis.store

    @pytest.mark.asyncio
    async def test_claim_overrides_redis_cache(self):
        redis = FakeRedis()
        redis.store["roles:u1"] = '["cloud_admin"]'
        rr = RoleResolver(roles_claim="roles", redis=redis, casdoor=None)
        roles = await rr.resolve("u1", {"roles": ["cloud_viewer"]})
        assert roles == ["cloud_viewer"]
        assert redis.store["roles:u1"] == '["cloud_viewer"]'

    @pytest.mark.asyncio
    async def test_claim_change_same_user_does_not_reuse_old_cache(self):
        redis = FakeRedis()
        rr = RoleResolver(roles_claim="roles", redis=redis, casdoor=None)

        first = await rr.resolve("u1", {"roles": ["cloud_admin"]})
        second = await rr.resolve("u1", {"roles": ["cloud_viewer"]})

        assert first == ["cloud_admin"]
        assert second == ["cloud_viewer"]
        assert redis.store["roles:u1"] == '["cloud_viewer"]'

    @pytest.mark.asyncio
    async def test_redis_cache_hit_when_claim_empty(self):
        redis = FakeRedis()
        redis.store["roles:u1"] = '["cloud_admin"]'
        rr = RoleResolver(roles_claim="roles", redis=redis, casdoor=None)
        roles = await rr.resolve("u1", {"roles": []})
        assert roles == ["cloud_admin"]

    @pytest.mark.asyncio
    async def test_claim_names_object(self):
        redis = FakeRedis()
        rr = RoleResolver(roles_claim="roles", redis=redis, casdoor=None)
        roles = await rr.resolve(
            "u1",
            {"roles": [{"name": "cloud_admin"}, {"displayName": "cloud_ops"}]},
        )
        assert set(roles) == {"cloud_admin", "cloud_ops"}

    @pytest.mark.asyncio
    async def test_casdoor_fallback_when_claim_empty(self):
        redis = FakeRedis()

        class FakeCasdoor:
            def configured(self) -> bool:
                return True

            async def get_user_roles(self, user_id: str, bearer_token=None):
                assert user_id == "u1"
                return ["cloud_viewer"]

        rr = RoleResolver(roles_claim="roles", redis=redis, casdoor=FakeCasdoor())
        roles = await rr.resolve("u1", {"roles": []})
        assert roles == ["cloud_viewer"]
        assert redis.store["roles:u1"] == '["cloud_viewer"]'

    @pytest.mark.asyncio
    async def test_no_redis_works(self):
        rr = RoleResolver(roles_claim="roles", redis=None, casdoor=None)
        roles = await rr.resolve("u1", {"roles": "cloud_ops"})  # string normalized
        assert roles == ["cloud_ops"]

    @pytest.mark.asyncio
    async def test_invalidate(self):
        redis = FakeRedis()
        redis.store["roles:u1"] = '["cached"]'
        rr = RoleResolver(roles_claim="roles", redis=redis, casdoor=None)
        await rr.invalidate("u1")
        assert "roles:u1" not in redis.store
