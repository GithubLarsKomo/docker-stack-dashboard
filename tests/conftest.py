import importlib

import fastapi.staticfiles
import pytest


class _DummyStaticFiles:
    async def __call__(self, scope, receive, send):
        raise RuntimeError("static files are not exercised in characterization tests")


@pytest.fixture(scope="session")
def dashboard_module():
    """Import app.main without requiring the container-only /app/static path."""
    original = fastapi.staticfiles.StaticFiles
    fastapi.staticfiles.StaticFiles = lambda *args, **kwargs: _DummyStaticFiles()
    try:
        module = importlib.import_module("app.main")
    finally:
        fastapi.staticfiles.StaticFiles = original
    return module
