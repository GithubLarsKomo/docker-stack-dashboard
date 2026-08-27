def test_role_classification_characterization(dashboard_module):
    d = dashboard_module
    assert d.role("ollama") == "llm-runtime"
    assert d.role("pubmed-mcp") == "mcp"
    assert d.role("postgres-db") == "internal"
    assert d.role("migration-job") == "job"
    assert d.role("totally-unknown") == "unknown"


def test_criticality_characterization(dashboard_module):
    d = dashboard_module
    assert d.critical("ollama") == "high"
    assert d.critical("pubmed-mcp") == "medium"
    assert d.critical("postgres-db") == "medium"
    assert d.critical("totally-unknown") == "low"


def test_localcurl_treats_auth_and_method_codes_as_reachable(monkeypatch, dashboard_module):
    d = dashboard_module

    for code in (401, 403, 405, 426):
        monkeypatch.setattr(d, "run", lambda *args, _code=code, **kwargs: (0, f"body\nHTTP_CODE:{_code}", ""))
        result = d.localcurl("http://service/mcp")
        assert result["ok"] is False
        assert result["reachable"] is True
        assert result["http_code"] == code


def test_localcurl_marks_successful_sse_as_ok(monkeypatch, dashboard_module):
    d = dashboard_module
    monkeypatch.setattr(d, "run", lambda *args, **kwargs: (0, "event: endpoint\ndata: /message\nHTTP_CODE:200", ""))
    result = d.localcurl("http://service/sse", sse=True)
    assert result["ok"] is True
    assert result["reachable"] is True


def test_mcp_discovery_preserves_reachable_handshake_semantics(monkeypatch, dashboard_module):
    d = dashboard_module
    monkeypatch.setattr(d, "running", lambda n: True)
    monkeypatch.setattr(d, "pick", lambda names, net=d.NETWORK: "probe")
    monkeypatch.setattr(d, "cand_ports", lambda n: [8000])
    monkeypatch.setattr(d, "same", lambda a, b: True)

    calls = []

    def fake_curl(src, url, method="GET", payload="", sse=False):
        calls.append((method, url))
        if url.endswith("/mcp"):
            return {
                "source": src,
                "url": url,
                "method": method,
                "http_code": 405,
                "ok": False,
                "reachable": True,
                "exit": 0,
                "ms": 1,
                "error": "",
                "sample": "",
            }
        return {
            "source": src,
            "url": url,
            "method": method,
            "http_code": 404,
            "ok": False,
            "reachable": False,
            "exit": 0,
            "ms": 1,
            "error": "",
            "sample": "",
        }

    monkeypatch.setattr(d, "curl", fake_curl)
    result = d.discover_mcp("pubmed-mcp", ["probe", "pubmed-mcp"])

    assert result["transport"] == "streamable-http"
    assert result["best"]["http_code"] == 405
    assert "Handshake" in result["recommendation"]
    assert len(calls) == 2


def test_service_discovery_is_serial_until_first_success(monkeypatch, dashboard_module):
    d = dashboard_module
    monkeypatch.setattr(d, "running", lambda n: True)
    monkeypatch.setattr(d, "pick", lambda names: "probe")
    monkeypatch.setattr(d, "cand_ports", lambda n: [8000])
    monkeypatch.setattr(d, "same", lambda a, b: True)

    calls = []

    def fake_curl(src, url, method="GET", payload="", sse=False):
        calls.append(url)
        ok = url.endswith("/ready")
        return {
            "source": src,
            "url": url,
            "method": method,
            "http_code": 200 if ok else 404,
            "ok": ok,
            "reachable": ok,
            "exit": 0,
            "ms": 1,
            "error": "",
            "sample": "",
        }

    monkeypatch.setattr(d, "curl", fake_curl)
    result = d.discover_service("unknown-service", ["probe", "unknown-service"])

    assert result["best"]["url"].endswith("/ready")
    assert calls == [
        "http://unknown-service:8000/health",
        "http://unknown-service:8000/healthz",
        "http://unknown-service:8000/ready",
    ]
