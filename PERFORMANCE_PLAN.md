# Performance Optimization Plan

## Problem and objective

`docker-stack-dashboard` currently performs Docker inspection, service/MCP discovery, status aggregation and UI refreshes through a compact but increasingly coupled FastAPI application. The first optimization cycle must establish a reproducible functional and performance baseline before code changes, then reduce redundant Docker CLI/process work without changing the externally visible classification and status behavior.

Primary objective for optimization v1:

- make `/api/status` measurably cheaper and more predictable,
- preserve functional behavior for container, service and MCP classification,
- create regression evidence before structural refactoring,
- prepare a safe path toward a cached Docker snapshot and bounded discovery engine.

This plan follows the Skillz `optimize-software-performance` and `performance-optimization-plan` workflow: baseline first, then hotspots, architecture review, small implementation slices, verification and simplification.

## Current baseline status

No measured runtime baseline is committed yet. All performance observations below are hypotheses until T001 instrumentation is executed against a representative host.

Repository evidence already indicates likely cost drivers:

- repeated `docker inspect` calls through helper functions such as `nets`, `state`, `health`, `labels`, `published` and `exposed`,
- repeated subprocess creation through `docker`, `docker exec`, `curl`, `docker stats` and `nvidia-smi`,
- nested endpoint discovery loops across candidate ports and paths,
- 30-second browser polling that can overlap with manual refreshes,
- a single `main.py` containing configuration, Docker access, probing, analysis, prompt generation and API routing.

## Functional invariants

Optimization must preserve the following behavior unless a later task explicitly changes a product requirement:

1. Existing `/api/status` response fields and semantics remain compatible.
2. Existing service classification remains functionally equivalent for known services.
3. Existing MCP classification and transport detection remain functionally equivalent.
4. HTTP 401/403/405/426 handling for MCP remains interpreted as reachable where currently intended.
5. Existing prompt generation remains available.
6. Existing Docker network/container summaries remain available.
7. Existing JSON export remains available.
8. No write-capable Docker operation is introduced as part of the optimization cycle.

## Performance dimensions to measure

T001 must record at minimum for `/api/status`:

- wall-clock response time,
- count of all subprocess executions,
- count of `docker ps`,
- count of `docker inspect`,
- count of `docker port`,
- count of `docker exec`,
- count of `docker stats`,
- count of local `curl` calls,
- count of TCP probes,
- count of HTTP/MCP probes,
- number of containers processed,
- response size,
- peak process RSS where practical.

Measurements must be repeated on the same host/workload at least three times after a warm-up request. Report median and range rather than a single timing.

## Representative workloads

At least three characterization fixtures are required:

### W1 — healthy mixed stack

Representative running containers including:

- one known classical HTTP service,
- one known TCP service,
- one MCP service,
- one internal infrastructure container,
- the dashboard container itself.

### W2 — degraded stack

Include at least:

- one exited container,
- one restarting or unhealthy container,
- one known service whose endpoint is unavailable,
- one MCP endpoint returning a reachable-but-not-success status such as 401/403/405/426.

### W3 — unknown/discovery-heavy stack

Include containers that do not match `SERVICE_HINTS`, have multiple candidate exposed/published ports and force deeper endpoint discovery.

W3 is the primary workload for proving or disproving the expected discovery hotspot.

## Initial hotspot hypotheses

These are not accepted as proven until T001/T002 measurement.

### H1 — repeated Docker inspect

Expected issue: each helper independently calls `inspect(n)`, multiplying Docker CLI process startup and JSON parsing per container.

Expected optimization direction: one batched inspection snapshot per refresh cycle.

Confidence: high.

### H2 — serial discovery fan-out

Expected issue: service/MCP discovery serially explores multiple ports and paths and may invoke `docker exec ... curl` for each candidate.

Expected optimization direction: fast-path known endpoints, bounded candidate set, result cache/TTL and later bounded concurrency where justified.

Confidence: high.

### H3 — overlapping refreshes

Expected issue: automatic 30-second refresh plus manual refresh can overlap, multiplying expensive scans.

Expected optimization direction: coalesce/lock refreshes and expose last successful refresh metadata.

Confidence: medium.

### H4 — architecture coupling increases optimization risk

Expected issue: Docker access, probing, analysis and API behavior are tightly coupled in `main.py`, making optimization changes harder to isolate and test.

Expected optimization direction: characterization tests first, then minimal extraction around the dominant hotspot rather than broad rewrite.

Confidence: high.

## Selected optimization sequence

### Slice T001 — Characterization and baseline

No production behavior change. Add deterministic tests/fixtures and lightweight instrumentation that can count subprocess/probe operations and capture baseline metrics.

### Slice T002 — Docker snapshot

Replace repeated per-helper inspection with a request-scoped/batched Docker snapshot while preserving response semantics.

Target structural gate:

- `docker inspect` subprocess count changes from repeated per-field/per-container use to at most one batched inspect subprocess per snapshot cycle, excluding explicitly documented exceptional paths.

### Slice T003 — Probe engine

Introduce ordered fast-path discovery, bounded deep discovery and TTL reuse for stable endpoint findings.

### Slice T004 — Security boundary

Harden default bind behavior and isolate Docker access behind a dedicated adapter. Evaluate least-privilege/socket-proxy options separately; do not pretend `:ro` socket mounting alone is sufficient isolation.

### Slice T005 — Minimal modularization

Extract only validated module boundaries needed to keep Docker snapshot, probes, analysis and API logic independently testable.

### Slice T006 — Frontend refresh control

Move inline JS to `app.js`, prevent overlapping refresh work, add error/backoff/last-success state and preserve current UI behavior.

### Slice T007 — CI/deployment guards

Add linting, tests, Docker build/config checks and security-oriented dependency/container scanning.

### Slice T008 — Simplification and documentation

Remove obsolete helpers/workarounds exposed by the new snapshot/probe model, then update README, configuration examples and architecture/security documentation.

## Rejected alternatives for v1

### Full framework rewrite

Rejected because there is no evidence that FastAPI or Vanilla JS is the bottleneck. A rewrite would increase risk without addressing the currently visible process/discovery costs.

### Immediate async conversion of all code

Rejected until measurements show blocking probe fan-out dominates after redundant work is removed. Async code would add complexity before the dominant avoidable work is quantified.

### Introduce Redis/cache infrastructure

Rejected for v1. Endpoint discovery cache should first be in-process and bounded. New infrastructure is unjustified unless a later multi-instance deployment requires shared state.

### Hard absolute latency target before baseline

Rejected because the repository does not yet contain a representative measured baseline. The first gate is structural and comparative.

## Risks

- characterization fixtures may not accurately represent the real AI/MCP host,
- mocks may hide Docker CLI/version-specific behavior,
- caching discovery can introduce stale endpoint data,
- bounded concurrency can alter probe ordering or load services more aggressively,
- refactoring before characterization could silently change status semantics.

## Measurement and benchmark plan

1. Establish fixture-level unit characterization for classification and discovery semantics.
2. Add subprocess/probe counters around the existing implementation without changing decision logic.
3. Run W1/W2/W3 baseline against a representative Docker host.
4. Record results in `performance-baseline.json` and a human-readable baseline note.
5. Repeat identical workload after each optimization slice.
6. Reject a slice if functional output changes without explicit approval.
7. After T002 and T003, compare both timing and operation-count metrics.

## Rollback

Each optimization slice must be independently revertible. Avoid combining Docker snapshot refactoring, discovery caching and concurrency in one commit. If a slice fails a functional gate, revert or repair only that slice before proceeding.

## Definition of Done for optimization v1

The cycle is complete when:

- T001 baseline evidence is committed,
- repeated Docker inspection is eliminated or quantitatively justified,
- discovery cost is reduced for unchanged services without breaking endpoint/MCP semantics,
- functional characterization tests pass,
- before/after metrics are documented using the same workload,
- CI runs the regression suite,
- simplification removes obsolete compatibility/workaround code introduced by the previous architecture,
- remaining performance/security trade-offs are documented explicitly.
