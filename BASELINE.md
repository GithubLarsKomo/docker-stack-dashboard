# T001 Baseline

## Scope

This baseline characterizes the current implementation before optimization. It intentionally does not change the Docker access architecture or probe algorithm.

## Structural baseline captured in tests

The characterization suite records these current properties:

- container metadata accessors call `docker inspect` independently;
- five accessors (`state`, `health`, `nets`, `published`, `exposed`) therefore produce five `docker inspect` subprocesses for the same container;
- `same(a, b)` currently performs two independent `docker inspect` subprocesses;
- service discovery probes serially until the first successful endpoint;
- MCP HTTP 401/403/405/426 responses are treated as reachable but not healthy;
- existing role and criticality classification is frozen by characterization tests;
- subprocess exceptions are converted to the current `(1, '', error)` return contract.

These are characterization facts, not yet optimization targets beyond the already-approved T002 batched-inspect gate.

## Runtime latency baseline

A live runtime measurement must be taken on the actual Docker host because GitHub repository analysis alone cannot reproduce the local container topology, service latency, GPU state, Docker daemon load, or network behavior.

Install test dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Run characterization tests:

```bash
python -m pytest -q
```

Measure `/api/status` using the same running stack and workload before and after every optimization slice:

```bash
python scripts/measure_status.py --url http://127.0.0.1:8088/api/status --runs 10
```

Record at least:

- successful/failed runs;
- min/median/p95/max wall-clock latency;
- response size;
- container count and stack state at measurement time;
- any timeouts or probe failures.

## T002 hard gate

After T001 is verified, T002 may begin. Its first structural performance gate is:

- at most one batched `docker inspect` subprocess per normal snapshot cycle, except explicitly documented exceptional/error paths;
- unchanged characterization semantics for status, classification and probing.

## Status

Repository-side T001 scaffold is implemented. Live measurements and test execution remain to be run in the target environment before T001 can be marked verified.
