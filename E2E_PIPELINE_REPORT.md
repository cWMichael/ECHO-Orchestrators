# E2E Pipeline Validation Report
Date: 2026-05-29 (Friday)

## Summary
Overall: **PARTIAL**

Live browser/API validation could not be completed in this session. The Cursor agent shell returned no output for all commands (`echo`, `netstat`, `uv run python launcher.py`). Browser navigation to `http://127.0.0.1:7860` failed with `chrome-error://chromewebdata/`; CDP `fetch('http://127.0.0.1:8020/health')` returned `TypeError: Failed to fetch`. Services were not running on :8020/:7860 at test time.

What was verified instead:
- Static wiring of Gradio UI → FastAPI gates (Gate 0/1/2) matches backend architecture
- All three `projects.json` target paths exist on disk
- Prior CLI pipeline runs (`run_pipeline.py`, documented in `SESSION_LOG.md`) completed backend tasks with Ollama, branch creation, diff, commit, and push to `ECHO_C_KI`
- Persistent task store (`temp/state.json`) holds 3 completed tasks with Unicode in descriptions

**Blocker for full PASS:** start launcher locally and re-run browser + API tests (see Recommendations).

## Test Environment
| Item | Status |
|------|--------|
| Agent workspace | `E:\Projects\ECHO-Orchestrators\ECHO-Orchestrators` |
| Shell execution | **FAILED** (empty stdout, no exit codes) |
| Backend :8020 | **DOWN** at test time |
| Gradio UI :7860 | **DOWN** at test time |
| Ollama :11434 | **Not probed** (backend down) |
| `RUNTIME_REPORT.md` | Not present |
| Launcher logs (`logs/launcher/`, `logs/backend/`, `logs/ui/`) | Not present (only `logs/echo_metrics.jsonl`) |

## Test Results
| # | Test | Result | Notes |
|---|------|--------|-------|
| 1 | Small Backend Task (planner → Gate 0 → Gate 1 → diff → reject → re-run → commit) | **SKIP (live)** / **PASS (historical)** | Live UI/API blocked. Historical: task `a459bd6c` completed via CLI; branch `feature/echo-a459bd6c` in `E:\Projects\ECHO_C_KI`, commit `7a96235`, push to origin (see `SESSION_LOG.md`, `temp/state.json`, `echo_metrics.jsonl`). Planner path not re-tested live. |
| 2 | Frontend/Docs Task (docs_worker, Unicode in diff panel) | **SKIP (live)** / **PARTIAL (code)** | `DocsWorker` is **MOCK** — returns fixed Markdown, writes `docs/README.md` artifact without Ollama/git diff. Unicode in `TaskPayload.description` is supported in JSON/store (`f\u00fcr` in state.json). Diff panel display not verified in browser. |
| 3 | Error Case (invalid/empty task, UI error, no hang) | **SKIP (live)** / **PASS (static)** | API: `title` min 3, `description` min 10, `PlanRequest.intent` min 10 → FastAPI 422. Planner failures → HTTP 502 `PlannerError`. UI: empty chat message skips API call, returns poll status (no hang by design). Live error UX not verified. |
| 4 | Project Switch (echo_c_ki, passwort_tool, cyberflow) | **PARTIAL** | All paths exist: `E:\Projects\ECHO_C_KI`, `E:\Projects\Passwort-Tool`, `E:\Projects\cyberFlow`. `POST /api/v1/projects/active` + `GET /api/v1/projects/active` implemented via `project_registry.resolve_project_path()`. Runtime switch uses in-memory `_project_root_override` — lost on server restart. **Cross-contamination risk:** orchestrator repo still contains `app/` tree and 7 `feature/echo-*` branches from pre-fix runs; target repo `ECHO_C_KI` has correct isolated branch. Live switch not API-tested. |
| 5 | Multiple Tasks Sequential (same UI session) | **SKIP** | Requires running Gradio + multi-task plan approval. `_advance_task()` in `control_ui.py` advances `active_task_idx` after each gate completion — logic present, not exercised live. |
| 6 | Approval Flow (all gates) | **PASS (static)** | See Gate Flow Verification below. UI button labels match backend gate semantics. |
| 7 | Logs Review | **PARTIAL** | `logs/echo_metrics.jsonl`: 11 entries, 7 successful Ollama backend runs (~18–24 s). No `logs/launcher/`, `logs/backend/`, `logs/ui/` (launcher not run this session). `temp/state.json`: 3 tasks, all `completed`. No restart loops observed in artifacts. Task history UI not verified live. |

## Reproducible Issues

### E1 — Agent shell unavailable (session blocker)
- **Symptom:** All `Shell` tool invocations return empty output with no exit code; subagent reported "Execution backend unavailable."
- **Impact:** Cannot start launcher, run `curl`/httpx, or execute lifecycle scripts from agent.
- **Workaround:** Run tests locally (see Recommendations).

### E2 — Services not running during browser test
- **Symptom:** `http://127.0.0.1:7860` → connection error; CDP fetch to :8020 fails.
- **Impact:** All Gradio UI test cases blocked.
- **Workaround:** `uv run python launcher.py --no-browser` then re-run browser tests.

### E3 — Diff/branch maps not persisted (known, pre-existing)
- **Location:** `core_router.py` — `_task_branches`, `_task_diffs` are in-memory only.
- **Impact:** After backend `--reload` or restart during Gate 2, diff may be empty (404/empty diff) even if task status is `pending_diff` in `state.json`.
- **Severity:** Stability issue for long Ollama runs, not a UI wiring bug.

### E4 — Legacy product code in orchestrator repo
- **Symptom:** `E:\Projects\ECHO-Orchestrators\ECHO-Orchestrators\app\` exists with worker-generated files; 7 local `feature/echo-*` branches.
- **Cause:** Tasks submitted before `PROJECT_ROOT` pointed exclusively to target repos.
- **Impact:** Confusing if someone inspects orchestrator repo expecting control-layer only.

### E5 — DocsWorker is mock
- **Symptom:** `docs_worker` does not call Ollama; returns canned Markdown.
- **Impact:** Test case 2 cannot validate real doc generation or meaningful git diff for docs tasks.

## Gate Flow Verification

Architecture (backend) vs UI labels — **aligned**:

| Gate | Backend | UI control | API endpoint | Status transition |
|------|---------|------------|--------------|-------------------|
| **Gate 0** | Plan approval | "Plan freigeben (Gate 0)" / "Plan ablehnen" | `POST /api/v1/plan` → `POST /api/v1/plan/{id}/approve` | Pending plan → tasks submitted (`awaiting_approval`) or plan discarded |
| **Gate 1** | Worker execution approval | "Gate 1: Worker starten" / "Gate 1: Ablehnen" | `POST /api/v1/tasks/{id}/approve` | `awaiting_approval` → worker runs → `pending_diff` or `completed`/`failed`; reject → `rejected`, branch deleted |
| **Gate 2** | Diff commit approval | "Gate 2: Commit + Push" / "Gate 2: Verwerfen" | `POST /api/v1/tasks/{id}/approve-diff` | `pending_diff` → `completed` (commit+push) or `rejected` (discard branch) |

UI status mapping (`control_ui.py` `STATUS_LABELS`):
- `awaiting_approval` → "waiting_for_approval" + hint "Gate 1: Worker freigeben?"
- `pending_diff` → diff panel populated via `GET /tasks/{id}/diff` + hint "Gate 2: Diff committen?"
- Polling every 3 s via `gr.Timer(3)`

**Note:** User brief mentioned "Diff approve/reject" under Gate 1 — actual implementation correctly places diff approval at **Gate 2**. UI documentation in `CONTROL_UI.md` is correct.

Gate 1 reject flow (`gate1(approved=False)`): calls API reject, advances to next task via `_advance_task()`.

Gate 2 reject flow: calls `approve_diff(approved=False)`, discards branch, advances task queue.

## Project Isolation

| Project ID | Path | Exists | Git repo | Evidence of ECHO branches |
|------------|------|--------|----------|---------------------------|
| `echo_c_ki` | `E:\Projects\ECHO_C_KI` | Yes | Yes, remote origin | `feature/echo-a459bd6c` committed+ pushed |
| `passwort_tool` | `E:\Projects\Passwort-Tool` | Yes | Yes | Not tested in this session |
| `cyberflow` | `E:\Projects\cyberFlow` | Yes | Yes | Task titles reference cyberFlow; completed runs in state.json used `app/` layout (path depends on active project at submit time) |

**Active project mechanism:** `POST /api/v1/projects/active` validates path exists, sets `set_project_root_override()`, updates `_active_project_name`. Default from `.env`: `PROJECT_ROOT=E:\Projects\ECHO_C_KI`.

**Risk:** Project switch is session-scoped (in-memory). Concurrent tasks across projects are not isolated by design — single active `project_root` at a time.

## Stability Assessment

Does it feel like a real tool or demo script?

**CLI path (`run_pipeline.py`):** Real. Ollama integration works (~20 s per backend task), git branches/commits/pushes verified on `ECHO_C_KI`, metrics logged, gates enforced.

**Gradio UI path:** Wiring looks production-intent (httpx client, gate buttons, polling, project dropdown, history table). **Not live-verified** this session — cannot confirm end-to-end feel, error display, or session persistence under load.

**Launcher/runtime:** Documented and scripted (`launcher.py` v1.1.0, `scripts/test_launcher_lifecycle.ps1`) but not executed here. Missing log directories suggest launcher has not been run recently on this machine state.

**Verdict:** Core pipeline is beyond demo for CLI/API; browser control layer is **unconfirmed** until services run and UI tests pass.

## Recommendations
(Stability fixes only — no new features)

1. **Re-run this validation locally** with services up:
   ```powershell
   cd E:\Projects\ECHO-Orchestrators\ECHO-Orchestrators
   uv run python launcher.py --no-browser
   # Then open http://127.0.0.1:7860 and execute test cases 1–5
   ```
   Or: `powershell -ExecutionPolicy Bypass -File scripts\test_launcher_lifecycle.ps1`

2. **Persist `_task_branches` / `_task_diffs`** to `temp/state.json` (already noted as Stufe 5 in `SESSION_LOG.md`) — prevents Gate 2 breakage after reload during long Ollama runs.

3. **Remove stale `app/` tree and local feature branches** from the orchestrator repo to eliminate confusion with target-project isolation (manual git cleanup, not code change).

4. **Replace or clearly label DocsWorker mock** if docs tasks are part of production workflow — currently test case 2 cannot validate real doc diffs.

5. **Add `http://127.0.0.1:7860` to `.env` `CORS_ORIGINS`** if browser preflight issues appear (config default includes it, but `.env` override may omit it).

## Artifacts Reviewed
- `control_ui.py`, `core_router.py`, `planner_router.py`, `CONTROL_UI.md`, `projects.json`
- `temp/state.json`, `logs/echo_metrics.jsonl`, `SESSION_LOG.md`, `.env`
- Git: `E:\Projects\ECHO_C_KI\.git\refs\heads\feature\echo-a459bd6c`
- Browser: failed connection to :7860, CDP health fetch failed

## Cleanup
No test processes were started by this agent (shell unavailable). No cleanup required.
