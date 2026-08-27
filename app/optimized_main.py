"""T002A runtime wrapper: batch Docker inspect once per normal status snapshot.

The existing application remains in ``main.py``. This wrapper patches only the
Docker inspect access path so the optimization is small, reversible, and easy
to measure independently from probe-strategy changes planned for T002B.
"""

from contextvars import ContextVar

try:  # package import in tests
    from . import main as _main
except ImportError:  # top-level import under uvicorn in /app
    import main as _main


_raw_inspect = _main.inspect
_raw_collect = _main.collect
_inspect_snapshot = ContextVar("docker_inspect_snapshot", default=None)


def _load_inspect_snapshot(names):
    """Return a name -> docker inspect payload map using one subprocess.

    ``None`` means the batched command failed and callers should fall back to
    the legacy per-container inspect path. An empty dict is a valid snapshot
    for an empty container list.
    """
    unique_names = list(dict.fromkeys(n for n in names if n))
    if not unique_names:
        return {}

    payload = _main.j(["docker", "inspect", *unique_names], None)
    if payload is None:
        return None

    snapshot = {}
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            continue
        name = (item.get("Name") or "").lstrip("/")
        if not name and index < len(unique_names):
            name = unique_names[index]
        if name:
            snapshot[name] = item
    return snapshot


def inspect(name):
    snapshot = _inspect_snapshot.get()
    if snapshot is None:
        return _raw_inspect(name)
    return snapshot.get(name, {})


def prime_inspect_snapshot(names):
    """Prime one batched inspect snapshot and return a ContextVar token."""
    return _inspect_snapshot.set(_load_inspect_snapshot(names))


def reset_inspect_snapshot(token):
    _inspect_snapshot.reset(token)


def collect():
    """Run the legacy collector with one batched Docker inspect snapshot.

    Probe logic, network discovery, logs, stats, response shape, and service/MCP
    classification are intentionally left unchanged in T002A.
    """
    rs = _main.rows()
    names = [r.get("Names", "") for r in rs if r.get("Names")]
    token = prime_inspect_snapshot(names)
    try:
        return _raw_collect()
    finally:
        reset_inspect_snapshot(token)


# Patch the original module because its FastAPI route functions resolve these
# globals at call time. Existing functions such as state(), nets(), same(),
# published(), exposed(), compose(), and dash_name() therefore transparently
# use the request-local snapshot without a broad rewrite.
_main.inspect = inspect
_main.collect = collect
_main.prime_inspect_snapshot = prime_inspect_snapshot
_main.reset_inspect_snapshot = reset_inspect_snapshot
_main._load_inspect_snapshot = _load_inspect_snapshot

app = _main.app
