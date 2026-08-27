import importlib

import fastapi.staticfiles
import pytest


class _DummyStaticFiles:
    async def __call__(self, scope, receive, send):
        raise RuntimeError("static files are not exercised in characterization tests")


@pytest.fixture(scope="session")
def dashboard_module():
    """Import app.main with the T002A runtime patch applied.

    Static files are replaced because the real /app/static path only exists in
    the container image.
    """
    original = fastapi.staticfiles.StaticFiles
    fastapi.staticfiles.StaticFiles = lambda *args, **kwargs: _DummyStaticFiles()
    try:
        module = importlib.import_module("app.main")
        importlib.import_module("app.optimized_main")
    finally:
        fastapi.staticfiles.StaticFiles = original
    return module
