# TASK — Optimization v1

## Objective

Establish a reproducible characterization/performance baseline for `docker-stack-dashboard`, then optimize the dominant verified costs in small reversible slices while preserving API/status semantics.

## Baseline

Current state before T001:

- single FastAPI application in `app/main.py`,
- Docker interaction primarily through repeated CLI subprocesses,
- endpoint/MCP discovery may probe multiple ports/paths serially,
- frontend refreshes `/api/status` every 30 seconds,
- no committed automated test suite or benchmark baseline,
- no committed operation-count metrics.

All current performance concerns are hypotheses until T001 measurements are recorded.

## Performance Gate

For T001, no improvement target is required. The gate is a reproducible baseline with operation counts and timing.

For T002, the first hard structural target is:

- reduce `docker inspect` to at most one batched subprocess per normal snapshot cycle, excluding explicitly documented exceptional/error paths,
- preserve status output compatibility under the characterization fixtures.

For later slices, use measured before/after results from the same workloads. Do not introduce arbitrary absolute latency targets without baseline evidence.

## Functional Gate

The following must remain functionally equivalent unless explicitly approved in a later task:

- `/api/status` schema and semantics,
- service classification,
- MCP classification and transport detection,
- reachable handling for MCP HTTP 401/403/405/426,
- container/network summaries,
- prompt generation,
- JSON export.

No Docker write action may be added.

## Scope

Included:

- characterization tests,
- baseline instrumentation,
- Docker subprocess/probe counting,
- benchmark harness or repeatable baseline script,
- representative fixtures,
- baseline documentation,
- subsequent snapshot/probe optimization slices after T001 passes.

## Out of Scope for T001

- production behavior refactor,
- asynchronous rewrite,
- new frontend framework,
- Redis/shared cache,
- Docker socket proxy rollout,
- authentication implementation,
- broad UI redesign.

## Constraints

- keep changes small and independently revertible,
- measure before optimizing,
- avoid network-dependent tests where deterministic fixtures suffice,
- do not require a live NVIDIA GPU for the core test suite,
- do not require destructive Docker operations,
- preserve compatibility with the current Docker CLI based deployment for T001,
- prefer Python for test/fixture/file-processing helpers where practical.

## T001 — Characterization & Baseline

### 1. Test scaffold

- [ ] Add test dependencies suitable for FastAPI and Python unit/integration tests (`pytest`, `httpx`; add async-specific tooling only if actually required).
- [ ] Create `tests/` structure.
- [ ] Add shared fixtures for Docker CLI responses and probe responses.
- [ ] Ensure tests can run without access to a real Docker daemon by default.

Expected files/components:

- `requirements-dev.txt` or equivalent development dependency declaration,
- `tests/conftest.py`,
- test modules listed below.

Verification:

- `pytest` runs locally without a Docker daemon,
- empty/fixture-based suite is deterministic.

### 2. Characterize container state helpers

- [ ] Add tests covering running, exited, restarting and missing containers.
- [ ] Characterize health states: healthy, unhealthy and no healthcheck.
- [ ] Characterize labels/compose metadata extraction.
- [ ] Characterize published/exposed port parsing.
- [ ] Characterize network extraction.

Suggested test file:

- `tests/test_container_characterization.py`

Functional gate:

- tests encode current expected semantics before refactor.

### 3. Characterize role and criticality classification

- [ ] Add known service classification fixtures for Ollama, n8n, OpenWebUI, MariaDB and dashboard.
- [ ] Add MCP-word classification examples.
- [ ] Add internal/job/unknown classification examples.
- [ ] Add criticality expectations for known and fallback roles.

Suggested test file:

- `tests/test_classification.py`

Functional gate:

- existing classification behavior is explicitly captured.

### 4. Characterize HTTP/TCP probe semantics

- [ ] Test successful HTTP responses.
- [ ] Test timeout/failure behavior.
- [ ] Test 401/403/405/426 reachable semantics.
- [ ] Test SSE body handling.
- [ ] Test TCP success/failure.
- [ ] Verify samples/errors are truncated/represented consistently.

Suggested test file:

- `tests/test_probes.py`

Functional gate:

- current `ok` vs `reachable` semantics are preserved.

### 5. Characterize service discovery

- [ ] Fixture: known service succeeds on preferred endpoint.
- [ ] Fixture: preferred endpoint fails and fallback endpoint succeeds.
- [ ] Fixture: no endpoint succeeds.
- [ ] Fixture: TCP service.
- [ ] Record the number/order of probe attempts as characterization evidence.

Suggested test file:

- `tests/test_service_discovery.py`

Functional gate:

- selected `best`, `recommendation` and endpoint result structure match current behavior.

### 6. Characterize MCP discovery

- [ ] Fixture: `/sse` success.
- [ ] Fixture: `/mcp` streamable HTTP success.
- [ ] Fixture: POST initialize success.
- [ ] Fixture: reachable-but-method/auth mismatch.
- [ ] Fixture: no MCP endpoint found.
- [ ] Record probe order/count.

Suggested test file:

- `tests/test_mcp_discovery.py`

Functional gate:

- transport classification and recommendation behavior remain compatible.

### 7. Characterize API output

- [ ] Add FastAPI test client coverage for `/api/status` using mocked Docker/probe data.
- [ ] Add coverage for `/api/prompts`.
- [ ] Add coverage for `/api/prompt` with valid and invalid/unknown component cases as currently implemented.
- [ ] Add coverage for `/api/export`.
- [ ] Capture a normalized representative `/api/status` fixture for regression comparison.

Suggested test file:

- `tests/test_api.py`

Functional gate:

- normalized response contract is committed as test evidence.

### 8. Add operation counters without changing decisions

- [ ] Introduce a minimal instrumentation layer around the existing `run()` path or equivalent seam.
- [ ] Count command families: `docker ps`, `docker inspect`, `docker port`, `docker exec`, `docker stats`, `curl`, `nvidia-smi`, other.
- [ ] Count HTTP, TCP and MCP probe attempts separately.
- [ ] Make counters accessible to tests/benchmark code without exposing them publicly by default.
- [ ] Ensure instrumentation can be disabled or has negligible overhead.

Expected component:

- preferably a small instrumentation helper/module; avoid broad production refactor in T001.

Verification:

- unit test proves counters match known fixture command sequence.

### 9. Create repeatable baseline runner

- [ ] Add a script/tool that performs warm-up plus at least three measured `/api/status` runs.
- [ ] Record wall time per run and median/range.
- [ ] Record command/probe counts for each run.
- [ ] Record container count and response size.
- [ ] Record peak RSS if practical and reliable in the target environment; otherwise mark it unavailable rather than guessing.
- [ ] Do not require destructive Docker access.

Suggested file:

- `tools/benchmark_status.py`

Output:

- `performance-baseline.json`

### 10. Define and capture representative workloads

- [ ] W1 healthy mixed stack fixture.
- [ ] W2 degraded stack fixture.
- [ ] W3 unknown/discovery-heavy fixture.
- [ ] Document which workload requires a live Docker host and which are synthetic fixtures.

Suggested location:

- `tests/fixtures/`

### 11. Record T001 results

- [ ] Run complete test suite.
- [ ] Run baseline on the representative real host if available.
- [ ] Commit `performance-baseline.json` with environment metadata that is safe for a public repository.
- [ ] Do not commit hostnames, private IPs, tokens, credentials or sensitive container configuration.
- [ ] Add a short `BASELINE.md` summarizing median/range and dominant operation counts.
- [ ] Mark any unavailable measurement explicitly.

T001 completion gate:

- tests green,
- current behavior characterized,
- baseline reproducible,
- operation counts available,
- likely hotspot ranking updated from measured evidence.

## T002 — Docker Snapshot

Do not start until T001 is complete.

- [ ] Design a request/snapshot-scoped container data model from the existing `docker ps` + inspect data.
- [ ] Batch `docker inspect` for all relevant containers in one command where supported.
- [ ] Refactor `nets/state/health/labels/published/exposed/compose` to consume snapshot data rather than invoking inspect independently.
- [ ] Preserve fallback/error behavior for disappearing containers.
- [ ] Run characterization suite.
- [ ] Repeat W1/W2/W3 benchmark.
- [ ] Prove `docker inspect` subprocess target.
- [ ] Document before/after timing and operation counts.

Rollback:

- keep T002 isolated from discovery caching/concurrency so the snapshot change can be reverted independently.

## T003 — Probe Engine

Do not start until T002 evidence is reviewed.

- [ ] Rank known-service endpoints before generic discovery.
- [ ] Reduce candidate ports/paths using observed container metadata.
- [ ] Add bounded in-process TTL caching for stable discovery results.
- [ ] Define invalidation conditions: container restart/change, port/network change, failed cached endpoint, TTL expiry.
- [ ] Consider bounded concurrency only after avoidable probes are removed.
- [ ] Preserve MCP reachable/transport semantics.
- [ ] Benchmark W3 in particular.

Performance gate:

- fewer deep probes for unchanged services,
- no functional regression,
- no unbounded concurrency.

## T004 — Security Boundary

- [ ] Change default published bind to localhost unless explicitly configured otherwise.
- [ ] Isolate Docker access behind a dedicated adapter/module.
- [ ] Document that Docker socket access is administrative-equivalent risk.
- [ ] Evaluate a read-limited socket proxy/allowlist deployment option.
- [ ] Keep production dashboard read-only in behavior.
- [ ] Add security tests/config validation where practical.

## T005 — Minimal Modularization

- [ ] Extract configuration.
- [ ] Extract Docker snapshot/client boundary.
- [ ] Extract probe/discovery logic.
- [ ] Extract classification/findings logic only where tests support the boundary.
- [ ] Keep `main.py` focused on app assembly/routes.
- [ ] Avoid framework rewrite.

## T006 — Frontend Refresh Control

- [ ] Move inline JS to `app/static/app.js`.
- [ ] Prevent overlapping refresh requests.
- [ ] Add timeout/error/backoff handling.
- [ ] Show last successful refresh.
- [ ] Preserve current tabs/features.
- [ ] Add lightweight accessibility/keyboard checks.

## T007 — CI and Deployment Guards

- [ ] Add linting/format checks appropriate to the codebase.
- [ ] Run `pytest` in CI.
- [ ] Run Docker image build in CI.
- [ ] Run `docker compose config` validation.
- [ ] Add dependency/container vulnerability scans with sensible failure policy.
- [ ] Add Dependabot or equivalent dependency update automation if desired.

## T008 — Simplification and Documentation

- [ ] Remove obsolete inspect/probe helpers superseded by the snapshot/probe engine.
- [ ] Remove temporary instrumentation not required for regression guards.
- [ ] Keep useful benchmark/regression tooling.
- [ ] Update README clone/install instructions.
- [ ] Add `.env.example`/configuration documentation.
- [ ] Add architecture and security notes.
- [ ] Document benchmark methodology and before/after results.

## Final Verification

- [ ] Run all functional tests after cleanup.
- [ ] Repeat identical W1/W2/W3 benchmark.
- [ ] Compare baseline vs final operation counts and timing.
- [ ] Verify no Docker write actions were introduced.
- [ ] Verify no secrets/internal host data are committed.
- [ ] Record residual risks and consciously deferred candidates.

## Expected Closure Documentation

Create/update `optimization-closure.md` with:

- baseline vs final metrics,
- functional test evidence,
- measured performance gain,
- security/deployment changes,
- simplifications performed,
- regression guards,
- remaining uncertainties and deferred work.
