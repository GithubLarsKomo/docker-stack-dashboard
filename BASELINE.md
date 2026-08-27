# T001 Baseline

## Scope

This baseline characterizes the implementation before optimization. It intentionally does not mix Docker access optimization with probe-strategy changes.

## Structural baseline captured in tests

Before T002A, the characterization suite established these properties:

- container metadata accessors called `docker inspect` independently;
- five accessors (`state`, `health`, `nets`, `published`, `exposed`) produced five `docker inspect` subprocesses for the same container;
- `same(a, b)` performed two independent `docker inspect` subprocesses;
- service discovery probes serially until the first successful endpoint;
- MCP HTTP 401/403/405/426 responses are treated as reachable but not healthy;
- existing role and criticality classification is frozen by characterization tests;
- subprocess exceptions are converted to the current `(1, '', error)` return contract.

## Verified runtime baseline

Target environment:

- Ubuntu Docker host;
- 52 containers visible to the dashboard;
- 39 running, 1 restarting, 12 exited at the captured status snapshot;
- dashboard served on `127.0.0.1:8088`;
- baseline measured with the real Docker socket, networks and service/MCP probes.

Characterization suite before optimization:

```text
9 passed in 0.02s
```

Three successful `/api/status` runs:

```text
run=1  54699.1 ms  155588 bytes
run=2  55333.7 ms  155582 bytes
run=3  54904.2 ms  155412 bytes
```

Aggregate baseline:

| Metric | Value |
| --- | ---: |
| successful runs | 3/3 |
| failed runs | 0 |
| min | 54.699 s |
| median | 54.904 s |
| p95 | 55.334 s |
| max | 55.334 s |
| response bytes min | 155,412 |
| response bytes median | 155,582 |
| response bytes max | 155,588 |

The narrow spread confirms a reproducible system-level cost rather than a single transient outlier.

## Observed dominant costs

The captured response also provides concrete evidence for later T002B work, without changing that logic in T002A:

- SSE probes can occupy roughly the full 5 s timeout even after receiving a valid endpoint event;
- `duckduckgo-mcp` explores many fallback port/path combinations serially;
- `docling-mcp` continues probing after repeated `421 Invalid Host header` responses;
- the original collector repeatedly executes Docker metadata lookups for the same containers.

T002A addresses only the last item.

## T002A hard gate

T002A introduces a request-local Docker inspect snapshot while intentionally preserving the existing probe algorithm.

Required structural gate:

- at most one batched `docker inspect` subprocess per normal snapshot cycle;
- direct legacy fallback remains available if the batched inspect fails;
- status, service/MCP classification and probe semantics remain unchanged;
- characterization tests remain green.

Implementation uses `app/optimized_main.py` as a narrow runtime wrapper around the existing application. `Dockerfile` starts `optimized_main:app`; the original `main.py` remains the behavioral baseline.

## T002A verification procedure

On the Ubuntu Docker host after pulling/rebuilding the branch:

```bash
python -m pytest -q
docker compose up -d --build
python scripts/measure_status.py --url http://127.0.0.1:8088/api/status --runs 3
```

Record the T002A result separately before starting T002B. No probe-strategy changes should be merged into this measurement.

## Status

T001 is verified. T002A implementation is committed and awaits target-host test/build/runtime measurement.
