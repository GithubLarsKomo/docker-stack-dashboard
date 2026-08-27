import json
from types import SimpleNamespace


def _inspect_item(name="svc"):
    return {
        "Id": f"{name}-abcdef1234567890",
        "Name": f"/{name}",
        "State": {"Status": "running", "Health": {"Status": "healthy"}},
        "Config": {
            "Labels": {
                "com.docker.compose.project": "demo",
                "com.docker.compose.service": "svc",
            },
            "ExposedPorts": {"8080/tcp": {}},
        },
        "NetworkSettings": {
            "Networks": {"ai-stack": {"IPAddress": "172.20.0.10"}},
            "Ports": {"8080/tcp": [{"HostPort": "18080"}]},
        },
    }


def test_snapshot_accessors_share_one_batched_docker_inspect(monkeypatch, dashboard_module):
    """T002A gate: repeated accessors use one batched inspect snapshot."""
    d = dashboard_module
    calls = []

    def fake_subprocess_run(cmd, capture_output, text, timeout):
        calls.append(tuple(cmd))
        if cmd[:2] == ["docker", "inspect"]:
            names = cmd[2:]
            payload = [_inspect_item(name) for name in names]
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(d.subprocess, "run", fake_subprocess_run)

    token = d.prime_inspect_snapshot(["svc"])
    try:
        assert d.state("svc") == "running"
        assert d.health("svc") == "healthy"
        assert "ai-stack" in d.nets("svc")
        assert d.published("svc") == {8080: [18080]}
        assert d.exposed("svc") == [8080]
        assert d.compose("svc")["project"] == "demo"
    finally:
        d.reset_inspect_snapshot(token)

    inspect_calls = [c for c in calls if c[:2] == ("docker", "inspect")]
    assert inspect_calls == [("docker", "inspect", "svc")]


def test_same_network_uses_existing_batched_snapshot(monkeypatch, dashboard_module):
    """T002A gate: same(a,b) performs no additional inspect subprocesses."""
    d = dashboard_module
    calls = []

    def fake_subprocess_run(cmd, capture_output, text, timeout):
        calls.append(tuple(cmd))
        if cmd[:2] == ["docker", "inspect"]:
            payload = [_inspect_item(name) for name in cmd[2:]]
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(d.subprocess, "run", fake_subprocess_run)

    token = d.prime_inspect_snapshot(["a", "b"])
    try:
        assert d.same("a", "b") is True
    finally:
        d.reset_inspect_snapshot(token)

    inspect_calls = [c for c in calls if c[:2] == ("docker", "inspect")]
    assert inspect_calls == [("docker", "inspect", "a", "b")]


def test_failed_batch_falls_back_to_legacy_inspect(monkeypatch, dashboard_module):
    """A race/failure in batched inspect must preserve legacy behavior."""
    d = dashboard_module
    calls = []

    def fake_subprocess_run(cmd, capture_output, text, timeout):
        calls.append(tuple(cmd))
        if cmd == ["docker", "inspect", "svc"] and len(calls) == 1:
            return SimpleNamespace(returncode=1, stdout="", stderr="synthetic batch failure")
        if cmd == ["docker", "inspect", "svc"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps([_inspect_item("svc")]), stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(d.subprocess, "run", fake_subprocess_run)

    token = d.prime_inspect_snapshot(["svc"])
    try:
        assert d.state("svc") == "running"
    finally:
        d.reset_inspect_snapshot(token)

    inspect_calls = [c for c in calls if c[:2] == ("docker", "inspect")]
    assert len(inspect_calls) == 2


def test_run_returns_error_tuple_on_subprocess_exception(monkeypatch, dashboard_module):
    d = dashboard_module

    def boom(*args, **kwargs):
        raise TimeoutError("synthetic timeout")

    monkeypatch.setattr(d.subprocess, "run", boom)
    code, stdout, stderr = d.run(["docker", "inspect", "svc"], timeout=1)

    assert code == 1
    assert stdout == ""
    assert "synthetic timeout" in stderr
