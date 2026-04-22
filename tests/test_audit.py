from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest

from app.audit import AuditWriter
from tests.factories import make_auth_ctx


class _FakeSession:
    def __init__(self, bucket):
        self.bucket = bucket

    def add(self, entry):
        self.bucket.append(entry)

    async def commit(self):
        return None


def _factory(bucket):
    @asynccontextmanager
    async def sm():
        yield _FakeSession(bucket)

    return sm


@pytest.mark.asyncio
async def test_audit_writer_captures_fields():
    bucket: list = []
    writer = AuditWriter(_factory(bucket))
    trace = uuid.uuid4()
    ctx = make_auth_ctx(user_id="u1", roles=["cloud_admin"], email="u1@x.com")

    await writer.log(
        trace_id=trace,
        ctx=ctx,
        tool_name="kb.search",
        arguments={"query": "hello", "token": "secret"},
        status="ok",
        tool_id=42,
        sensitive_fields_hit=["token"],
        latency_ms=17,
    )

    assert len(bucket) == 1
    row = bucket[0]
    assert row.user_id == "u1"
    assert row.roles == ["cloud_admin"]
    assert row.tool_id == 42
    assert row.tool_name == "kb.search"
    assert row.status == "ok"
    assert row.latency_ms == 17
    assert "token" in row.sensitive_fields_hit
    assert row.arguments == {"query": "hello", "token": "secret"}
    assert row.trace_id == trace


@pytest.mark.asyncio
async def test_audit_writer_swallows_db_errors(caplog):
    class _Boom:
        def add(self, _):
            raise RuntimeError("db down")

        async def commit(self):
            raise RuntimeError("db down")

    @asynccontextmanager
    async def sm():
        yield _Boom()

    writer = AuditWriter(sm)
    # Should not raise even when underlying DB errors.
    await writer.log(
        trace_id=uuid.uuid4(),
        ctx=make_auth_ctx(),
        tool_name="x",
        arguments={},
        status="denied",
        deny_reason="not_found_or_no_role",
    )
