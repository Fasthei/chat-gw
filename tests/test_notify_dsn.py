from __future__ import annotations

from app.db.notify import _parse_asyncpg_dsn


def test_strips_sqlalchemy_driver_prefix():
    dsn, kw = _parse_asyncpg_dsn("postgresql+asyncpg://db.example/mydb")
    assert dsn == "postgresql://db.example/mydb"
    assert kw == {}


def test_plain_postgresql_scheme_passes_through():
    dsn, kw = _parse_asyncpg_dsn("postgresql://db.example:5432/mydb")
    assert dsn == "postgresql://db.example:5432/mydb"
    assert kw == {}


def test_ssl_require_hoisted_to_kwarg():
    dsn, kw = _parse_asyncpg_dsn(
        "postgresql+asyncpg://db.example:5432/mydb?ssl=require"
    )
    assert dsn == "postgresql://db.example:5432/mydb"
    assert kw == {"ssl": "require"}


def test_ssl_true_normalised_to_require():
    _, kw = _parse_asyncpg_dsn("postgresql+asyncpg://db.example/mydb?ssl=true")
    assert kw == {"ssl": "require"}


def test_sslmode_remains_in_dsn():
    dsn, kw = _parse_asyncpg_dsn(
        "postgresql+asyncpg://db.example:5432/mydb?sslmode=require"
    )
    assert dsn == "postgresql://db.example:5432/mydb?sslmode=require"
    assert kw == {}


def test_preserves_other_query_params_alongside_ssl():
    dsn, kw = _parse_asyncpg_dsn(
        "postgresql+asyncpg://db.example/mydb?application_name=chatgw&ssl=require"
    )
    assert "application_name=chatgw" in dsn
    assert "ssl=" not in dsn
    assert kw == {"ssl": "require"}
