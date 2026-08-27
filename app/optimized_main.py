"""Runtime optimizations layered over the characterized v5 implementation.

T002A batches Docker inspect once per normal status snapshot.
T002B keeps the existing discovery semantics but removes avoidable probe cost:

- known/advertised ports are tried before any guesses;
- containers with no advertised port are not blindly scanned by default;
- legacy deep fallback discovery is opt-in with ``DEEP_DISCOVERY=1``;
- MCP protocol responses 406/421 count as reachable configuration/handshake
  signals, like the already-characterized 401/403/405/426 responses;
- SSE discovery stops as soon as the first endpoint event is received instead
  of waiting for the normal five-second curl timeout.

The original ``main.py`` remains the behavioral baseline so every optimization
slice stays small and reversible.
"""

from contextvars import ContextVar
import os
import time

try:  # package import in tests
    from . import main as _main
except ImportError:  # top-level import under uvicorn in /app
    import main as _main


_raw_inspect = _main.inspect
_raw_collect = _main.collect
_raw_curl = _main.curl
_raw_localcurl = _main.localcurl
_inspect_snapshot = ContextVar("docker_inspect_snapshot", default=None)
DEEP_DISCOVERY = os.getenv("DEEP_DISCOVERY", "0").strip().lower() in {"1", "true", "yes", "on"}
_REACHABLE_PROTOCOL_CODES = {401, 403, 405, 406, 421, 426}
_LEGACY_FALLBACK_PORTS = [80, 3000, 3001, 3002, 3010, 5000, 5050, 5678, 7474, 7860, 7861, 8000, 8008, 8080, 8088, 11434]


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


def _hint_port(name):
    hint = next((h for h in _main.SERVICE_HINTS.values() if name in h["match"]), None)
    if not hint:
        return None
    try:
        return int(hint.get("port"))
    except (TypeError, ValueError):
        return None


def cand_ports(name):
    """Return a small, evidence-based ordered port list.

    T002B deliberately avoids the old 16-port blind scan when Docker exposes no
    port metadata. Operators who need that legacy behavior can opt in with
    ``DEEP_DISCOVERY=1``.
    """
    ports = []

    def add(port):
        try:
            port = int(port)
        except (TypeError, ValueError):
            return
        if port not in ports:
            ports.append(port)

    add(_hint_port(name))
    for port in _main.exposed(name):
        add(port)
    for port in _main.published(name).keys():
        add(port)

    if ports:
        return ports
    if DEEP_DISCOVERY:
        return list(_LEGACY_FALLBACK_PORTS)
    return []


def _upgrade_reachable(result):
    if result.get("http_code") in _REACHABLE_PROTOCOL_CODES:
        result["reachable"] = True
    return result


def _sse_result(source, url, method, started, code, stdout, stderr):
    body = (stdout or "").strip()
    event_seen = body.startswith("event:") or "\nevent:" in body
    if event_seen and code is None:
        # The early-exit pipeline intentionally stops curl before its trailing
        # -w status formatter could run. A valid MCP endpoint event is itself
        # sufficient evidence of a successful HTTP SSE connection.
        code = 200
    reachable = event_seen or code in _REACHABLE_PROTOCOL_CODES or (code is not None and 200 <= code < 400)
    return {
        "source": source,
        "url": url,
        "method": method,
        "http_code": code,
        "ok": bool(event_seen or (code is not None and 200 <= code < 400)),
        "reachable": bool(reachable),
        "exit": 0 if event_seen else 1,
        "ms": int((time.time() - started) * 1000),
        "error": "" if event_seen else (stderr or "")[-700:],
        "sample": body[:1000],
    }


def curl(src, url, method="GET", payload="", sse=False):
    """Use legacy curl normally; terminate SSE after the first event frame."""
    if not sse:
        return _upgrade_reachable(_raw_curl(src, url, method, payload, sse=False))

    # MCP SSE announces the message endpoint in its first event. ``head`` then
    # closes the pipe, so curl need not hold the streaming connection for the
    # full TIMEOUT. A curl broken-pipe exit is intentionally accepted when the
    # event frame was captured.
    inner = (
        "curl --noproxy '*' -sS --no-buffer "
        f"--max-time {_main.TIMEOUT} '{url}' | head -n 2"
    )
    started = time.time()
    c, out, err = _main.run(["docker", "exec", src, "sh", "-lc", inner], _main.TIMEOUT + 3)
    result = _sse_result(src, url, method, started, None, out, err)
    if not result["ok"]:
        result["exit"] = c
    return result


def localcurl(url, method="GET", payload="", sse=False):
    """Local variant of :func:`curl` with the same SSE early-exit behavior."""
    if not sse:
        return _upgrade_reachable(_raw_localcurl(url, method, payload, sse=False))

    inner = (
        "curl --noproxy '*' -sS --no-buffer "
        f"--max-time {_main.TIMEOUT} '{url}' | head -n 2"
    )
    started = time.time()
    c, out, err = _main.run(["sh", "-lc", inner], _main.TIMEOUT + 2)
    result = _sse_result("dashboard", url, method, started, None, out, err)
    if not result["ok"]:
        result["exit"] = c
    return result


def collect():
    """Run the legacy collector with the T002A/T002B runtime patches."""
    rs = _main.rows()
    names = [r.get("Names", "") for r in rs if r.get("Names")]
    token = prime_inspect_snapshot(names)
    try:
        return _raw_collect()
    finally:
        reset_inspect_snapshot(token)


# Patch globals resolved by the original FastAPI route functions at call time.
_main.inspect = inspect
_main.cand_ports = cand_ports
_main.curl = curl
_main.localcurl = localcurl
_main.collect = collect
_main.prime_inspect_snapshot = prime_inspect_snapshot
_main.reset_inspect_snapshot = reset_inspect_snapshot
_main._load_inspect_snapshot = _load_inspect_snapshot

app = _main.app
