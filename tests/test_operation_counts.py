import json
from types import SimpleNamespace


def _inspect_payload():
    return [
        {
            "Id": "abcdef1234567890",
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
    ]


def test_repeated_container_access_currently_repeats_docker_inspect(monkeypatch, dashboard_module):
    """T001 structural baseline: five accessors currently spawn five inspect subprocesses."""
    d = dashboard_module
    calls = []

    def fake_subprocess_run(cmd, capture_output, text, timeout):
        calls.append(tuple(cmd))
        if cmd[:2] == ["docker", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps(_inspect_payload()), stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(d.subprocess, "run", fake_subprocess_run)

    assert d.state("svc") == "running"
    assert d.health("svc") == "healthy"
    assert "ai-stack" in d.nets("svc")
    assert d.published("svc") == {8080: [18080]}
    assert d.exposed("svc") == [8080]

    inspect_calls = [c for c in calls if c[:2] == ("docker", "inspect")]
    assert len(inspect_calls) == 5


def test_same_network_currently_requires_two_inspects(monkeypatch, dashboard_module):
    """T001 structural baseline for same(a,b)."""
    d = dashboard_module
    calls = []

    def fake_subprocess_run(cmd, capture_output, text, timeout):
        calls.append(tuple(cmd))
        return SimpleNamespace(returncode=0, stdout=json.dumps(_inspect_payload()), stderr="")

    monkeypatch.setattr(d.subprocess, "run", fake_subprocess_run)

    assert d.same("a", "b") is True
    assert len([c for c in calls if c[:2] == ("docker", "inspect")]) == 2


def test_run_returns_error_tuple_on_subprocess_exception(monkeypatch, dashboard_module):
    d = dashboard_module

    def boom(*args, **kwargs):
        raise TimeoutError("synthetic timeout")

    monkeypatch.setattr(d.subprocess, "run", boom)
    code, stdout, stderr = d.run(["docker", "inspect", "svc"], timeout=1)

    assert code == 1
    assert stdout == ""
    assert "synthetic timeout" in stderr
