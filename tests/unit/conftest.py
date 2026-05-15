"""Unit test conftest — mock missing modules (httpx, fastapi) for offline runs.

Placed in tests/unit/ so it loads before any unit test file imports from services.
Inside conftest.py, the mocks are set via sys.modules before any test module loads,
so all imports from services/*/app/main.py succeed without needing real httpx/fastapi.
"""

import sys
from unittest.mock import MagicMock

# ── Mock httpx ─────────────────────────────────────────────────────────────
if 'httpx' not in sys.modules:
    _httpx_mock = MagicMock()
    _httpx_mock.HTTPStatusError = type('HTTPStatusError', (Exception,), {})
    _httpx_mock.AsyncClient = MagicMock()
    _httpx_mock.Response = MagicMock()
    sys.modules['httpx'] = _httpx_mock

# ── Mock FastAPI with identity decorators ─────────────────────────────────
#   @app.get/@app.post/@app.api_route must preserve the decorated function
#   (not replace it with a MagicMock), or asyncio.run(handler(...)) fails:
#   "ValueError: a coroutine was expected, got <MagicMock>"
if 'fastapi' not in sys.modules:

    class _FastAPIMock:
        def __init__(self, *args, **kwargs):
            super().__init__()

        def get(self, *args, **kwargs):
            return lambda f: f

        def post(self, *args, **kwargs):
            return lambda f: f

        def api_route(self, *args, **kwargs):
            return lambda f: f

        def add_middleware(self, *args, **kwargs):
            pass

        def __call__(self, *args, **kwargs):
            return self

    _fastapi_mock = MagicMock()
    _fastapi_mock.FastAPI = _FastAPIMock
    sys.modules['fastapi'] = _fastapi_mock
    sys.modules['fastapi.middleware'] = MagicMock()
    sys.modules['fastapi.middleware.cors'] = MagicMock()
