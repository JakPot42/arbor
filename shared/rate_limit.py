"""shared/rate_limit.py — one slowapi Limiter instance, shared by main.py
(which registers it on app.state) and any router whose routes need
`@limiter.limit(...)` (currently only CFIUS's /intake, ported from
cfius_screener's own rate-limited intake route)."""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
