#!/usr/bin/env python3
"""Mint a dev JWT for local chat-gw testing.

Usage:
    python scripts/make_dev_token.py                     # default: cloud_admin
    ROLES=cloud_viewer python scripts/make_dev_token.py  # override roles
    SUB=alice python scripts/make_dev_token.py           # override subject
    EXP=7200 python scripts/make_dev_token.py            # override TTL (seconds)

Reads `JWT_DEV_SECRET` and `JWT_DEV_ALGORITHM` from env; falls back to
`.env.example` defaults.
"""
from __future__ import annotations

import os
import sys
import time

try:
    from jose import jwt
except ImportError:
    sys.stderr.write("python-jose not installed; run `pip install -r requirements.txt`\n")
    sys.exit(1)


def main() -> int:
    secret = os.environ.get("JWT_DEV_SECRET", "dev-secret-change-me-in-production")
    algorithm = os.environ.get("JWT_DEV_ALGORITHM", "HS256")
    audience = os.environ.get("JWT_AUDIENCE", "chat-gw")
    issuer = os.environ.get("JWT_ISSUER") or None
    sub = os.environ.get("SUB", "dev-user")
    roles = [r for r in os.environ.get("ROLES", "cloud_admin").split(",") if r]
    ttl = int(os.environ.get("EXP", "3600"))

    payload: dict = {
        "sub": sub,
        "roles": roles,
        "email": os.environ.get("EMAIL", f"{sub}@example.com"),
        "name": os.environ.get("NAME", sub),
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl,
        "aud": audience,
    }
    if issuer:
        payload["iss"] = issuer

    print(jwt.encode(payload, secret, algorithm=algorithm))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
