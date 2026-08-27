# Performance Baseline and Optimization Measurements

## Scope

This document tracks measured performance on the real Ubuntu Docker host. Optimization slices are kept separate so each improvement can be attributed to one change set.

## T001 — verified baseline

Target environment:

- Ubuntu Docker host;
- 52 containers visible to the dashboard;
- 39 running, 1 restarting, 12 exited at the captured status snapshot;
- dashboard served on `127.0.0.1:8088`;
- real Docker socket, networks and service/MCP probes.

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

Aggregate T001 baseline:

| Metric | Value |
| --- | ---: |
| successful runs | 3/3 |
| failed runs | 0 |
| min | 54.699 s |
| median | 54.904 s |
| p95 | 55.334 s |
| max | 55.334 s |
| response bytes median | 155,582 |

Structural characterization established that repeated metadata access caused many independent `docker inspect` subprocesses and that service/MCP discovery was serial.

## T002A — verified batched Docker inspect

T002A introduced a request-local Docker inspect snapshot through `app/optimized_main.py`. `Dockerfile` runs `optimized_main:app`; the original `main.py` remains the behavioral baseline.

Measured three-run result on the same Docker host:

```text
run=1  36978.8 ms  155574 bytes
run=2  36696.0 ms  155562 bytes
run=3  36672.6 ms  155410 bytes
```

Aggregate T002A:

| Metric | T001 | T002A | Change |
| --- | ---: | ---: | ---: |
| min | 54.699 s | 36.673 s | -33.0% |
| median | 54.904 s | 36.696 s | -33.2% |
| p95 | 55.334 s | 36.979 s | -33.2% |
| max | 55.334 s | 36.979 s | -33.2% |
| response bytes median | 155,582 | 155,562 | effectively unchanged |
| failed runs | 0/3 | 0/3 | unchanged |

Median wall-clock time improved by **18.208 s (-33.2%)**, roughly **1.50x faster**, while response size stayed effectively unchanged.

T002A hard gate is therefore verified:

- normal status collection uses one batched inspect snapshot;
- legacy direct inspect remains as fallback if batch loading fails;
- response generation remains successful on the real 52-container stack.

## Remaining observed cost after T002A

The remaining ~36.7 s median is dominated by probe/discovery behavior rather than Docker metadata collection. The captured T001/T002A responses show concrete examples:

- SSE endpoints can hold a valid connection until the 5 s curl timeout even after returning the first `event: endpoint` frame;
- `duckduckgo-mcp` has no advertised HTTP port yet the legacy algorithm tries a broad generic port list and multiple MCP paths serially;
- MCP responses such as `406 Not Acceptable` and `421 Invalid Host header` prove that an MCP endpoint is present, but legacy discovery continues until a later 405/timeout or exhausts additional probes;
- known service ports are not always prioritized ahead of generic candidates.

## T002B — bounded fast probe strategy

T002B is implemented in `app/optimized_main.py` and deliberately leaves the original `main.py` unchanged.

Changes:

- known service-hint ports are tried first;
- exposed/published Docker ports are used as evidence-based candidates;
- no blind generic port scan is performed when a container advertises no ports;
- legacy broad fallback scanning is opt-in with `DEEP_DISCOVERY=1`;
- MCP HTTP 406 and 421 are treated as reachable protocol/configuration signals in addition to 401/403/405/426;
- SSE curl uses `--no-buffer` and terminates after the first two event-frame lines using `head -n 2`, avoiding the normal streaming timeout once an endpoint event has arrived.

### T002B performance gate

Required target on the same host/topology:

- median `/api/status` < **15 s**;
- stretch goal < **5 s**;
- no failed benchmark requests;
- JSON response remains valid;
- service/MCP detection remains the same or becomes more semantically correct (for example a 406/421 MCP response may now be classified as reachable instead of unknown);
- characterization/performance tests remain green.

Verification command:

```bash
python -m pytest -q
docker compose up -d --build
python scripts/measure_status.py --url http://127.0.0.1:8088/api/status --runs 3
```

## Status

- T001: verified.
- T002A: verified, median 36.696 s, -33.2% vs T001.
- T002B: implemented, awaiting target-host tests and runtime measurement.
