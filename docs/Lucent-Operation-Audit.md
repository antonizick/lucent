# Lucent Operation-Audit

**Date:** 2026-07-20
**Auditor:** Lucent (Claude Opus 4.8), against the live codebase at `/home/nick/dev/lucent` and the running process/port state on this host.
**Scope:** Architecture, security, reliability, scalability, maintainability, and improvement opportunities for the Lucent platform (Voice Box UI, auth proxy, hook/automation scripts, NERO self-improvement loop, three-tier memory, backup/git sync).

> **Method note:** Every finding below is grounded in a specific file/line or an observed runtime fact (port bindings, process list, git state). Nothing here is speculative about features that don't exist.

> ### Threat model (per Nick, 2026-07-20)
> **The host is network-isolated.** The *only* thing reachable from outside the isolated segment is the **MFA-authenticated UI on port 8002**, exposed via the tunnel. This is the correct lens for everything below, and it changes the ranking:
>
> - The **sole external attack surface is port 8002.** Therefore the security priority is not "what binds to `0.0.0.0`" in the abstract — it is **"what can an unauthenticated request to 8002 actually reach?"**
> - The answer is the crux of this audit: **8002's catch-all and several endpoints forward to 8001 *without* checking the session (S2), and 8001's backend has an unrestricted arbitrary-file-read (`/view-file`, S3).** Chained, that means a request to the internet-facing 8002 — with no credentials — can read any file the service user can read. **Network isolation does not mitigate this, because the vulnerable path is inside the one component that is deliberately exposed.** S2+S3 therefore remain **P0/Critical**.
> - Conversely, **S1 (services binding `0.0.0.0`) drops from Critical to a P1 hardening item**: on an isolated segment, `0.0.0.0` is only reachable by whatever else shares that segment, not the internet. Still worth fixing (defense-in-depth, and it's nearly free), but it is not the emergency — the tunnel-reachable bypass is.
> - **S4 (CORS)** is browser-delivered, so isolation doesn't fully neutralize it, but its practical reach is limited to a browser that can already reach the backend; downgraded to Medium.
> - **S5** (single isolated user) is genuine hardening, not urgent.
>
> Net: the isolation is real risk reduction and is to your credit — but it does **not** cover the S2→S3 chain, which is the finding that actually matters.

---

## 1. Executive Summary

Lucent is a genuinely capable, feature-rich personal-assistant platform. The memory architecture (three-tier daily→archive→LTMemory), the hook-driven context bootstrap, and the NERO reflection loop are well thought out, and there is real defensive engineering in places (the `guard_memory_write.py` PreToolUse hook and the staged-diff secret scanner in `backup_memory.py` are both good, incident-driven controls).

**Given the network-isolation context, the dominant problem narrows to one thing — but it is still serious.** The design intent (unauthenticated local UI on 8001, MFA gate on 8002, only 8002 tunneled out) is sound and the isolation genuinely reduces risk. The problem is that **the one component deliberately exposed to the internet, the 8002 proxy, does not actually enforce authentication on most paths, and it forwards to a backend that can read arbitrary files:**

- The "authenticated" proxy (`auth_proxy.py`) has a **catch-all route and several explicit endpoints that proxy to 8001 without checking the session** (S2). The MFA gate effectively guards only `/` and the `/auth/*` pages.
- The backend (`server.py`) has **no authentication on any of its ~70 routes**, including `/view-file`, an **unrestricted arbitrary-file-read** primitive (S3).
- Chained, an **unauthenticated request to the tunneled 8002** can read any file the service user can access (SSH keys, the auth `credentials.json`, `ui/.env`, email credentials). **This is the #1 thing to fix and it is reachable from the internet today, isolation notwithstanding.**

Lower-ranked, because isolation *does* help here: 8001 binding `0.0.0.0` (S1 — now hardening) and CORS `*`+credentials (S4 — browser-scoped).

Secondary themes: (2) the memory backup repo had bloated to **431 MB** because a 15 MB recall index was committed and pushed hourly — ✅ **fixed** (R1, `.git` now 3.0 MB); (3) near-zero automated test coverage over ~10k lines of platform scripts plus two large monolith web files — ✅ **fixed for the highest-risk seams** (M1, 64 tests + CI; broader coverage of the monolith files remains future work); (4) meaningful script sprawl / dead code that raises the maintenance cost of everything else; (5) environment hygiene issues — global pip installs ✅ **fixed** (R2, `ui/.venv` + full pinning), mixed root/user file ownership and stray junk directories still open (R3, M4).

### Severity & Priority Table

*(Severity/priority reflect the network-isolation threat model: only 8002 is externally reachable.)*

| # | Finding | Category | Severity | Effort | Priority |
|---|---------|----------|----------|--------|----------|
| S2 | `auth_proxy.py` catch-all & `/speak`/`/static` bypass session check — **tunnel-reachable** | Security | **Critical** | Med | ✅ **FIXED 2026-07-20** |
| S3 | `server.py` zero auth; `/view-file` = arbitrary file read — **reachable via S2 through 8002** | Security | **Critical** | Med | ✅ **FIXED 2026-07-20** |
| S1 | Services (8001/8110/8103) bind `0.0.0.0` — isolation limits blast radius | Security/Hardening | Med | Low | P1 |
| S4 | CORS `allow_origins=["*"]` + `allow_credentials=True` (browser-scoped) | Security | Med | Low | P1 |
| S5 | Weak password hashing (unsalted SHA-256) + insecure cookie flags + no rate limiting | Security | Med | Low–Med | P1/P2 |
| R1 | memory/.git = 431 MB; 15 MB `.recall_index.json` committed+pushed hourly | Reliability/Scale | High | Low | ✅ **FIXED 2026-07-20** (431MB→3MB) |
| R2 | No dependency isolation (no `ui/.venv`) or full pinning | Reliability | Med | Low | ✅ **FIXED 2026-07-20** |
| R3 | Mixed root/user file ownership; unclear service supervision | Reliability | Med | Med | P1 |
| M1 | Near-zero test coverage + no CI over core platform | Maintainability | High | Med–High | ✅ **DONE 2026-07-20** (Phases 1–3) |
| M2 | Script sprawl / dead code (dual compress paths, removed-but-present scripts, `.py`+`.sh` twins) | Maintainability | Med | Med | P2 |
| M3 | Monolithic files: `server.py` (~2.6k lines), `reflect.py` (831), `startup.py` (650) | Maintainability | Med | Med–High | P2 |
| M4 | Stray junk dirs (`--help/`, `append/`, `check/`, `scratch pad/` vs `scratchpad/`) | Hygiene | Low | Low | P2 |
| O1 | NERO loop observability & guardrails (auto-mode, model routing) | Opportunity | Med | Med | P2 |
| O2 | Health/self-healing consolidation into one supervisor | Opportunity | Med | Med | P3 |
| O3 | Recall index: incremental/on-disk vector store instead of 15 MB JSON reload | Opportunity/Perf | Med | Med | P3 |

---

## 1a. Remediation Log — 2026-07-20 (S2 + S3 closed)

The P0 tunnel-reachable chain (S2→S3) was remediated and verified the same day. **No commits were made** — changes are live in the working tree and running services; rollback is a file-restore + service restart (see `scratchpad/s2s3_rollback_20260720/`).

**Changes applied:**
1. **`ui/auth_proxy.py`** — added an `enforce_session` HTTP middleware: every path requires a valid, MFA-verified session cookie **except** `/auth/*`, `/services/health`, `/favicon.ico`. Browser navigations without a session → 302 to `/auth/login`; API calls → 401. This is a single choke-point, so no individual route can be left open again. Also fixed a latent proxy bug: the catch-all now **propagates the backend status code** (previously every proxied response — including 403/404/500 — was silently relabelled 200, which masked the S3 403).
2. **`ui/server.py`** — added `_is_allowed_file_path()` and applied it to `/view-file` and `/open-file`: paths must resolve under an allowlist (`memory, idea, logs, docs, presentation, scratchpad`). `resolve()` collapses `..`, so traversal out is blocked. Reading `/etc/passwd`, `~/.ssh`, or `ui/.auth/credentials.json` now returns 403 — even for an authenticated session (defense-in-depth).
3. **`ui/discord_bot.py` + `ui/discord_monitor.py`** — `BACKEND_URL` default moved `8002 → 8001` so local automation talks to the backend directly rather than through the now-locked proxy. (`startup.py` needed no change: `/services/health` stays public for its liveness probe, and `speak_both` already falls back to 8001.)

**Verification: 17/17 automated checks + 3 supplementary passed** (`scratchpad/verify_s2s3.py`), including a real end-to-end TOTP login:
- Attacker: unauth 8002 `/view-file?path=/etc/passwd`, `/api/todo`, `/speak`, catch-all → **401**; unauth browser `/` → **302 → login**. (Confirmed the 403 body carries no file contents — no leak.)
- Legit remote UI: e2e MFA login → cookie; authed `/`, `/api/todo`, `/static/app.js`, `/speak/stream` (SSE), allowed `/view-file` → **200**; `/etc/passwd` & `credentials.json` → **403**.
- Backend/voice unaffected: 8001 `/speak` → **200**; discord's new target `/discord/pending` on 8001 → **200**.

**User-validated in production (2026-07-20):** Nick confirmed remote Tailscale access to the UI **and** the Discord bridge both work perfectly after the fix — so the change is verified beyond the automated suite, against the real tunnel and real Discord path.

**Deferred (not done here):** binding the backend behind a proxy-only shared secret (would touch every direct 8001 caller — higher breakage risk; S1 localhost-bind covers the same exposure more cheaply). S1/S4/S5 remain as written.

**Rollback:** `cp scratchpad/s2s3_rollback_20260720/*.bak` back over the four `ui/` files (strip `.bak`), then `sudo systemctl restart lucent-voice-box.service lucent-auth.service discord-bot.service lucent-monitor.service`.

### R1 Phase A — 2026-07-20 (recall index untracked; growth stopped)

Non-destructive half of R1 done and pushed (memory commit `d2d625f`).

**Changes:** Added `memory/.gitignore` ignoring `.recall_index.json` / `.recall_index*` (+ transient SQLite sidecars `*.db-wal`, `*.db-shm`); `git rm --cached .recall_index.json`. Working-tree index untouched; regeneration verified (`python3 scripts/memory_index.py build` → 897 chunks in 4.5s). Future `git add -A` no longer stages the 15 MB index — confirmed by dry-run; the pushed backup commit was KB-sized.

**Result:** hourly bloat from the index is stopped. `.git` is still ~431 MB — history reclamation is Phase B (destructive, pending Nick's OK + backup).

**Correction to the R1 plan (found while measuring history):** per-path history totals show `.recall_index.json` (~79 MB across all revisions) is **not** the dominant contributor. The real bloat is the email DB churn — `email/email.db-wal` (~1.28 GB uncompressed across history), `email/email.db` (~1.01 GB), and `logs/email_sync.log` (~285 MB). Phase B targeted these paths too, not just the recall index.

### R1 Phase B — 2026-07-20 (history rewritten; space reclaimed) ✅ DONE

Destructive half executed with Nick's explicit go-ahead after a full backup + validated dry-run.

**Nick's decisions:** full purge of history for recall index + email DB (db/wal/shm) + rotating logs; **untrack email.db and the rotating logs going forward too** (email state accepted as no longer backed up — his explicit call); `logs/activity_*.log` kept tracked.

**Phase A extension (non-destructive, commit `2ff348a`):** `git rm --cached` + gitignore for `email/email.db`, `logs/cron.log`, `logs/email_sync.log`, `.nero/worker.log`.

**Backup (rollback):** full copy of `memory/` incl. `.git` at `/home/nick/lucent_r1_backup_20260720` (458 MB). Restore = `rm -rf memory && cp -a /home/nick/lucent_r1_backup_20260720 memory`.

**Rewrite:** `git filter-repo --force --invert-paths` over the 7 paths → `reflog expire` + `gc --prune=now --aggressive` → re-add origin → `git push --force`. **Result: `.git` 438 MB → 3.0 MB** (fresh clone from remote = 4.4 MB). fsck clean; all purged paths gone from every commit; LTMemory/core/MEMORY/daily notes/activity logs intact; working-tree `.recall_index.json` + `email.db` preserved on disk. 465 empty backup-only commits pruned (1719→1254); real content preserved. Upstream tracking restored; backup daemon push path verified clean.

**Note:** GitHub retains the old unreachable objects server-side until its own GC, but clients now clone the 4.4 MB repo. The `/home/nick/lucent_r1_backup_20260720` backup can be deleted once Nick is satisfied.

### R2 + M1 — 2026-07-20 (dependency isolation, security test suite, CI) ✅ DONE

Done in sequence per the roadmap (R2 first, so M1's suite runs in a clean, deterministic environment from day one). Model-switch gates observed: Sonnet 5 for R2, Opus 4.8 to design the Phase 1 security-test assertions, Sonnet 5 for bulk authoring + CI.

**R2 (dependency isolation):**
- Created `ui/.venv`; found and pinned several dependencies `ui/requirements.txt` never listed (`pyotp`, `aiohttp`, `discord.py`, `Flask`, `ddgs`, `piper-tts`, and a hidden FastAPI `Form()` dependency, `python-multipart` — caught by import-testing `auth_proxy.py` in the venv before touching anything live). Full 57-package `ui/requirements.lock` frozen and reproducibility-verified (a from-scratch venv built from the lock file alone reproduces a byte-identical environment).
- `ui/start.sh` now auto-creates and execs from `.venv` (the `exec` also collapses the old bash-wrapper PID layer, resolving the R3 process-ambiguity note below for the voice box specifically). `lucent-auth.service`'s `ExecStart` repointed at `ui/.venv/bin/python3` (required a one-off manual `sudo` edit — outside the passwordless sudoers scope).
- Verified end-to-end on the live services post-restart: `/speak` 200 direct and via proxy; S2/S3 protections unaffected (401/403/302 all still correct); real browser session traffic flowed clean through the restart with zero errors.
- `scripts/requirements.txt` added (pins `requests`/`questionary`/`rich`) — **documentation/pinning only, deliberately not wired into its own venv or into the `.claude/settings.json` hook commands.** Those hooks run on every turn of every session with no systemd-style rollback if a repoint goes wrong; the risk/benefit didn't clear the bar this session.

**M1 (test suite + CI), 64 tests total, all isolated from prod:**
- **Phase 1 — security tests** (Opus-designed, `tests/platform/test_auth_proxy_security.py` + `test_file_access_security.py`, 25 tests): pin the S2/S3 fixes above — unauthenticated `/view-file?path=/etc/passwd` through the proxy → 401 with no leak; `/static` and `/speak`'s stale "no auth needed" handlers are actually gated; a valid MFA session passes the gate (guards against an always-deny middleware); backend status-code propagation. Isolated via a stubbed `httpx.AsyncClient` + monkeypatched session store, so passing the gate hits a test stub, never the live voice box.
- **Phase 1 — memory-guard tests** (`test_guard_memory_write.py` + `test_backup_memory_guards.py`, 21 tests): `guard_memory_write.py`'s shrink guard tested via its real subprocess stdin/stdout contract; `backup_memory.py`'s secret-scan and shrink-scan tested against a real throwaway git repo under `tmp_path` (never `memory/.git`).
- **Phase 2 — hook smoke tests** (18 tests): `startup.py`'s individual check functions tested via a monkeypatched `LUCENT_ROOT` (running its full `main()` live was ruled out — real network calls, possible service restart, checkpoint writes, compression subprocess). `lucent-init.sh` — which hardcodes its own path with no override — tested by copying the entire real `scripts/` tree into a throwaway directory and running a patched copy of the hook against it, proving it survives a completely empty `memory/` dir without crashing.
- **Phase 3 — CI** (`.github/workflows/ci.yml`): installs from `ui/requirements.txt` + new `ui/requirements-dev.txt`, runs `tests/platform/` as the hard gate, `ruff` (scoped to real correctness rules — syntax errors, undefined names, redefinitions, not style) as informational only. `tests/email_system/` deliberately excluded — see finding below.

**Two bugs found incidentally while building the suite (not fixed — flagged for Nick):**
1. **`check_ltmemory_completeness` off-by-one** (`scripts/startup.py`): its bullet-counter (`session_content.count('\n-')`) undercounts by 1 because the regex-captured session text starts immediately after the header's own newline, so the first bullet line is never counted. A session with exactly 3 bullets — the threshold CLAUDE.md and the function's own docstring call sufficient — needs 4 in practice, or gets wrongly flagged as a stub, which can block startup. Pinned as a regression test in `tests/platform/test_startup_smoke.py` rather than silently fixed.
2. **`tests/email_system/` writes to the live daily note.** `src/lucent_email/email_service.py`'s `_confirm_send()` hardcodes `Path.home() / "dev/lucent/memory"` and appends to today's note directly via `open().write()` — outside the `subprocess.run` mock those tests use (which only covers the curl/voice call). Running the suite during this session's CI-scoping work wrote 5 fake "[Email] Sent... alice@example.com" lines into the real `memory/2026-07-20.md`; caught immediately (no real voice call fired), the lines were removed the same session. The suite also has 12/89 pre-existing failures unrelated to this work (e.g. a naive/aware-datetime bug), which is the other reason it's excluded from CI for now.

---

## 2. P0 — Security (the tunnel-reachable chain: fix first)

**The two P0 items (S2 + S3) are one exploit chain** — an unauthenticated request to the internet-facing 8002 reaches, via the proxy's missing session checks, the backend's arbitrary-file-read. Treat them as a single remediation workstream. S1 and S4 (below, now P1) are hardening that isolation already blunts. **Recommended model for the P0 work: Claude Opus 4.8** — security-boundary code where a subtle miss (an auth check that fails open) has high blast radius; not a place to economize.

### S1 *(P1 — hardening; isolation limits blast radius)* — Services bind `0.0.0.0`

**Observed:** `ss -tlnp` shows `0.0.0.0:8001` (voice box, PID 968 `uvicorn server:app`), `0.0.0.0:8002` (auth_proxy), plus `0.0.0.0:8110`, `0.0.0.0:8103`. Only `8104` (LCC) and `8114` (Sketchlab) correctly bind `127.0.0.1`. `auth_proxy.py:802` hard-codes `host="0.0.0.0"`.

**Why it still matters (in context):** On the isolated segment, `0.0.0.0` is not internet-reachable, so this is no longer critical. But binding the *unauthenticated* backend to all interfaces means anything else that ever lands on that segment (a second device, a future VM, a compromised neighbor service) reaches 8001 with no gate. It's defense-in-depth that costs nearly nothing and restores the design's stated "8001 = localhost only" invariant. Low effort, clear benefit, low urgency.

**What to change:** Bind the *unauthenticated* backend (8001) and any service that should be private to `127.0.0.1`. Keep only the MFA proxy (8002) reachable off-host, and only via the tunnel.

**How (technical approach):**
1. Change `server.py`'s uvicorn invocation (and `ui/start.sh`) to `--host 127.0.0.1`. The auth proxy reaches it via `http://localhost:8001` already (`auth_proxy.py:80`), so nothing legitimate breaks.
2. Audit the other `0.0.0.0` binders (8110 AIVU, 8103) and pin each to `127.0.0.1` unless it has a deliberate, documented reason to be public.
3. Add a host-firewall default-deny for inbound on the LAN interface (ufw/nftables), allowing only the tunnel interface. Belt-and-suspenders behind the tunnel ACL.
4. **Verify the tunnel scope:** confirm the Tailscale/tunnel config (see `scratchpad/LucentTailSetup.ps1`) only exposes 8002, not 8001. This is the assumption the whole design depends on and should be asserted, not presumed.

**Phased plan:** Phase 0 (single session): change binds → restart services via `restart-services.sh` → re-run `ss -tlnp` to confirm 8001/8110/8103 are `127.0.0.1` → curl 8002 login flow to confirm nothing broke. Dependency: none. Milestone: `ss` output shows only 8002 (and the tunnel) publicly bound.

---

### S2 — `auth_proxy.py` proxies to 8001 **without** verifying the session

**Observed (`ui/auth_proxy.py`):**
- `/speak` (L688), `/speak/stream` (L704), `/message/pending` (L732/L740) all forward to 8001 with a comment "*Port 8001 doesn't require authentication - auth is handled at the proxy level*" — but they perform **no** `verify_session_token` call.
- `/static/{path}` (L661): "*If no token, proxy directly*" (L667–670) — unauthenticated passthrough.
- The catch-all `@app.api_route("/{path:path}", ...)` (L747) proxies **any** method and **any** path straight to 8001 with **no session check at all** (L766–798).

**Why it matters:** The catch-all alone means every backend route (including `/view-file`, `/run-backup`, `/agent/invoke`, `/api/todo`) is reachable through the "authenticated" proxy *without authenticating*. The MFA gate only actually guards `/` and the `/auth/*` pages; everything else is open. This is a straightforward auth bypass in the component whose only job is authentication.

**What to change:** Enforce a verified, MFA-complete session on **every** proxied route by default; make "no auth" an explicit, minimal allowlist rather than the default behavior.

**How:**
1. Add a FastAPI dependency (or middleware) `require_session` that runs `verify_session_token(cookie_or_bearer)` and 401/redirects on failure.
2. Apply it to the catch-all and to `/speak`, `/speak/stream`, `/message/pending`, `/static` (static can stay unauthenticated only if it genuinely serves non-sensitive assets — but safer to gate it too).
3. Delete the "auth handled at proxy level" comments — they encode a false assumption that led directly to the bypass.
4. Add a regression test that hits `/view-file?path=/etc/passwd` through 8002 **without** a cookie and asserts 401.

**Phased plan:** Phase 1 depends on S1 being done first (so that while you're refactoring, 8001 isn't independently exposed). Milestone: unauthenticated request to any non-`/auth` path on 8002 returns 401/redirect; authenticated flow still works end-to-end.

---

### S3 — `server.py`: no authentication on ~70 routes; `/view-file` is arbitrary file read

**Observed:** `grep` for `auth|token|Depends` in `server.py` returns only an unrelated logging line — there is **no** auth anywhere in the backend. `/view-file` (L2314) does `Path(path).resolve()` with **no base-directory restriction**, then returns file contents or a directory listing. `/open-file` (L2363) resolves an arbitrary path and launches it via `subprocess.Popen`. `/run-backup` (L1837), `/agent/invoke` (L1944), `/reflect/apply` (L1393), and full `/api/todo` CRUD are all unauthenticated.

**Failure scenario (concrete):** `GET http://<host>:8001/view-file?path=/home/nick/dev/lucent/ui/.auth/credentials.json` returns the MFA secret and password hash. `?path=/home/nick/.ssh/id_rsa` returns the private key. Because of S1 (8001 on `0.0.0.0`) and S2 (proxy catch-all), this is reachable both directly and through the "authenticated" proxy.

**Why it matters:** This is the highest-impact single bug: a remote, unauthenticated arbitrary file read as the service user, plus unauthenticated trigger of privileged actions (backups, agent invocation, reflection apply). It converts the network-exposure problems into concrete data exfiltration.

**What to change:** Two layers — (a) put the backend behind auth (it should only ever be spoken to by the proxy), and (b) constrain `/view-file` and `/open-file` to an explicit allowlist of roots.

**How:**
1. Because 8001 is being pinned to localhost (S1) and the proxy will enforce sessions (S2), the *primary* fix is defense-in-depth: add a shared-secret header check between proxy→backend, or a localhost-only guard, so the backend refuses requests that didn't come through the proxy.
2. Harden `/view-file`: define `ALLOWED_ROOTS = [memory/, idea/, logs/, presentation/]`; after `resolve()`, reject any path not `is_relative_to` an allowed root (Python 3.9+: check via `os.path.commonpath`). Return 403 otherwise. Same for `/open-file`.
3. Gate the state-changing endpoints (`/run-backup`, `/agent/*`, `/reflect/*`, `/email/*`, `/api/todo` writes) behind the session dependency once the proxy forwards identity, or behind the proxy-shared-secret at minimum.
4. Add tests: allowed path succeeds; `../` traversal and absolute paths outside roots return 403.

**Phased plan:** Phase 1 (same workstream as S2). Milestone: `/view-file` outside allowed roots → 403; backend rejects non-proxy requests.

---

### S4 — CORS wildcard origin **with** credentials

**Observed (`ui/server.py:177-180`):** `CORSMiddleware` with `allow_origins=["*"]`, `allow_credentials=True`, `allow_methods=["*"]`.

**Verified during audit — the wildcard is NOT required for multi-URL / Tailscale access.** Two facts settle it:
1. **`auth_proxy.py` (port 8002, the tunneled component) has no CORS middleware at all.** The CORS config in question lives on `server.py` (8001), which the remote browser never contacts directly — it always goes through 8002.
2. **Every frontend request uses a *relative* path** (`fetch('/speak')`, `fetch('/api/todo')`, `new EventSource('/speak/stream')`, etc. — grep of `ui/static` confirms zero hardcoded origins). A relative URL resolves against **the origin that served the page**. So when the UI is loaded from `https://bld2.taild1bb43.ts.net/`, every API call goes back to that same `ts.net` origin → **same-origin, CORS never engages**. When loaded from the local Windows IP, calls go to that same IP → same-origin again.

The reason it *feels* like the wildcard is necessary is that the URLs look very different — but they are used **one at a time**, and in each case *page-origin == API-origin*. There is never a single request where the page is on origin A and the API is on origin B. CORS only governs that A→B case, which doesn't occur here.

**On the dynamic-IP worry specifically:** the browser derives `Origin` from the **hostname in the URL**, not the resolved IP. `bld2.taild1bb43.ts.net` is a **stable Tailscale DNS name** — it does not change when the Windows or WSL IP churns. So even if a genuine cross-origin need ever appeared, a one-line allowlist of that single stable hostname would cover *all* remote access permanently; the fluid IPs are irrelevant to Origin.

**Residual risk (why still worth changing):** `["*"]` + `allow_credentials=True` makes Starlette reflect *any* requesting Origin with `Access-Control-Allow-Credentials: true`. On 8001 that's low impact today (not remote-facing, isolated), which is why this sits at P1 — but it's dead, misleading config that will bite if the topology ever changes.

**What to change / how:** Set `allow_origins` to a concrete allowlist — `["https://bld2.taild1bb43.ts.net"]` plus any local origin you actually load the UI from — or, since the UI is entirely same-origin, **remove the middleware and confirm nothing breaks.** One-line change.

**How to verify safely (zero-risk test):** on a branch, set the allowlist (or remove CORS), restart the voice box, then load the UI over the `ts.net` URL and exercise Speak / TODO / a tab or two. Same-origin traffic is unaffected by the change, so a working UI confirms it. (Caveat: a few calls use `${BASE}/api/...` — the LCC/command-center backend; confirm `BASE` resolves to a relative path or `/lcc`, not a distinct external origin, before finalizing.)

**Phased plan:** Bundle with Phase 1 hardening. Milestone: UI works over `ts.net` with a scoped allowlist (or no CORS); untrusted origin gets no credentialed access.

---

## 3. P1 — High-value reliability & security hardening

### S5 — Password hashing, cookie flags, and no MFA rate limiting

**Observed:** `auth_proxy.py:47-50` hashes passwords with unsalted `hashlib.sha256` (the docstring itself says "use bcrypt/argon2 in production"). The session cookie (L567-574) is set `secure=False, httponly=False`. `verify_mfa` (L533) has no attempt counter or lockout.

**Assessment / worth it:** Yes, but lower urgency than P0 because in practice there's a single user and MFA is the real gate. Still cheap and removes standing risk — especially `httponly`/`secure` on a cookie that traverses an internet tunnel.

**What/how:**
- Swap SHA-256 → `argon2-cffi` or `bcrypt` (`passlib`). One function, plus a one-time re-hash of the stored credential.
- Set the cookie `secure=True, httponly=True, samesite="strict"`. `secure=True` is fine because the tunnel terminates TLS; confirm the browser reaches 8002 over HTTPS.
- Add a simple failed-MFA counter per username (in the sessions file or an in-memory dict) with exponential backoff / lockout.
- Note: password is currently only used at `/auth/setup`; the live login flow is username + TOTP (no password check at `/auth/authenticate`, L349). Consider whether that's intended — **username-only + TOTP means knowing the username + a valid 6-digit code is the entire gate.** Recommend adding password verification to the authenticate step, or documenting the decision.

**Model:** Sonnet 5 is sufficient (well-trodden patterns), Opus if bundling with the P0 auth refactor for consistency.

### R1 — Memory backup repo bloat: 431 MB `.git`, 15 MB index pushed hourly

**Observed:** `memory/.git` is **431 MB**. `.recall_index.json` (15 MB) is **tracked** and committed. `backup_memory.py` runs `git add -A` + commit + push hourly (per the memory-backup daemon), so a fresh 15 MB blob enters history every time the index changes — which is constantly. The staged-diff secret scanner also re-scans that 15 MB diff each run.

**Why it matters:** Unbounded repo growth → slow clones, slow pushes, wasted bandwidth/storage, and eventually GitHub's 1–2 GB soft limits. The index is a *derived artifact* — it should never be in version control. This is pure waste and it compounds every hour.

**What to change:** Stop tracking `.recall_index.json` (and any other derived caches) in the memory repo; shrink history.

**How:**
1. Add `.recall_index.json` (and `.recall_index*`) to `memory/.gitignore`; `git rm --cached memory/.recall_index.json`.
2. Rewrite history to purge the accumulated blobs: `git filter-repo --path .recall_index.json --invert-paths` (or BFG), then force-push. **Back up the repo first and confirm with Nick — this is a history rewrite (destructive to shared history).**
3. Confirm `memory_index.py` rebuilds the index locally on demand (it does: `python3 scripts/memory_index.py build`), so nothing is lost by removing it from the repo.
4. Optional: run `git gc --aggressive` after the purge.

**Phased plan:** Phase A (non-destructive, immediate): gitignore + `rm --cached` so it stops growing. Phase B (scheduled, with backup + Nick's OK): history rewrite to reclaim the 400 MB. Dependency: Phase B needs a confirmed backup of `memory/`. Milestone: `.git` back under ~30 MB; hourly pushes are KB-sized.

**Model:** Haiku 4.5 / Sonnet 5 — mechanical git surgery; the judgment call (history rewrite) is Nick's, not the model's.

### R2 — No dependency isolation or full pinning for the UI tier *(✅ FIXED 2026-07-20 — see §1a)*

**Observed:** No `ui/.venv` (checked — global installs). `ui/requirements.txt` pins fastapi/uvicorn but uses `>=` for anthropic/httpx/requests. Multiple other services (Tally, AIVU) *do* have their own `.venv`, so the core UI is the outlier.

**Why it matters:** Global installs mean a `pip install` for any other project can silently upgrade fastapi/uvicorn under the Voice Box and break it at the next restart — a classic hard-to-diagnose outage on a shared box. Reliability >> simplicity (your stated principle) argues for isolation here.

**What/how:** Create `ui/.venv`, `pip install -r requirements.txt` into it, fully pin (`pip freeze > requirements.lock`), and point `ui/start.sh` / the systemd unit at the venv's python. Do the same for the `scripts/` runtime if it has non-stdlib deps (ollama client uses `requests`).

**Phased plan:** One session; test by restarting the voice box from the venv and confirming `/speak` works. Milestone: `ps` shows the voice box running from `ui/.venv/bin/python`.

### R3 — Mixed file ownership and unclear supervision

**Observed:** `scratchpad/` contains **root-owned** files (`.png`, `.db`, `.rtf`) alongside user-owned ones — something in the pipeline occasionally runs as root. Service supervision is a mix of `.service` unit files (voice-box, monitor, discord), shell scripts (`restart-services.sh`, `lucent-service-manager.sh`), and manually-launched `uvicorn` processes (the voice box is `python3 -m uvicorn server:app` with no unit visible in the process args).

**Why it matters:** Root-owned files created by a normally-user service indicate an ambiguous execution context (cron-as-root? a sudo path?), which is both a reliability and a least-privilege concern. Inconsistent supervision means "is it running / will it come back after reboot?" has no single answer.

**What/how:** (1) Find what writes root-owned files (`grep` cron + systemd for the offending script) and make it run as `nick`, or `chown` and prevent recurrence. (2) Standardize: every long-lived service gets a systemd user unit with `Restart=on-failure`; kill the manual-launch path. `feedback_never_broad_process_kill` still applies — reconcile by PID/port. Milestone: reboot test → all services return; no new root-owned files appear.

### M1 — Near-zero automated test coverage + no CI *(✅ DONE 2026-07-20 — see §1a)*

**Observed:** The only tests are `tests/email_system/` (5 phase files). ~10k lines of `scripts/`, a ~2.6k-line `server.py`, and a ~800-line `auth_proxy.py` have **no** tests. No CI config present.

**Why it matters:** The system is safety-critical to *itself* — the 2026-07-17 daily-note wipe and the "unsummarized sessions" recurrence bug are both incidents that tests would have caught. Every refactor above (especially the P0 auth work) is riskier without a regression net.

**What to change:** Introduce a focused pytest suite around the highest-risk, most-testable seams first — not 100% coverage, but the load-bearing logic.

**How (priority order):**
1. **Security regression tests** (write these *as part of* the P0 fix): `/view-file` traversal blocked; unauthenticated proxy request → 401; CORS origin rejection.
2. **Memory-integrity tests:** `guard_memory_write.py` shrink logic; `backup_memory.py` secret scanner (`_looks_like_secret`, entropy) and shrink guard; compress/archive round-trip.
3. **Hook smoke tests:** `startup.py` / `lucent-init.sh` produce valid output and never crash on missing files.
4. Add a minimal GitHub Actions (or local pre-push) runner: `pytest -q` + `ruff`/`flake8`.

**Phased plan:** Phase 1 = the ~6 security + memory tests (highest ROI, gate the P0 merge on them). Phase 2 = hook smoke tests. Phase 3 = CI wiring. Milestone: `pytest` green in CI on push.

**Model:** **Sonnet 5** for the bulk test authoring (fast, cheap, pattern-heavy); **Opus 4.8** to design the security test cases so the assertions actually pin the boundary.

---

## 4. P2 — Maintainability & tech debt

### M2 — Script sprawl and dead code

**Observed in `scripts/`:** overlapping compression paths — `check_compression.py`, `compress_with_archive_validation.py`, `safe_compress.py`, `scan_uncompressed.py`, plus compression logic inside `backup_memory.py`. `enforce_unsummarized_sessions.py` still exists (348 lines) even though `lucent-init.sh:104` documents it as **REMOVED** ("produced garbage via regex"). Dual `ai-launcher.py`/`ai-launcher.sh` and `lucent.py`/launcher twins. Three overlapping startup validators: `validate_startup.py`, `verify_startup.py`, `validate_response.py`.

**Why it matters:** ~50 scripts with unclear ownership means every change requires re-deriving which script is actually wired in. Dead code that contradicts the live comments is an active trap for the next reader (human or AI).

**What/how:** Produce a one-page "script map": for each script, is it (a) wired to a hook/cron/service, (b) a CLI tool, or (c) dead. Delete/relocate (c) to an `archive/` or remove entirely. Consolidate the compression family into one module with one entry point. Cross-check against `.claude/settings.json` hooks, systemd units, and crontab to establish "wired" status.

**Phased plan:** Phase 1 = generate the map (grep hooks/cron/units for each filename). Phase 2 = delete confirmed-dead (starting with `enforce_unsummarized_sessions.py`). Phase 3 = consolidate compression. Milestone: script count down meaningfully; no script contradicts a live comment. **Model: Sonnet 5** (mechanical + judgment, low blast radius); have it propose deletions for Nick's confirmation rather than auto-deleting.

### M3 — Monolithic files

**Observed:** `server.py` ~2.6k lines / 92 KB spanning voice, email, reflection, security, ollama, todo, avatars, file-serving. `reflect.py` 831 lines, `startup.py` 650, `security_auditor.py` 686.

**Why it matters:** Large single-responsibility-violating files are hard to test (see M1), hard to reason about for security (S3 lives here), and raise merge/regression risk.

**What/how:** Split `server.py` into FastAPI routers by domain (`routers/voice.py`, `routers/email.py`, `routers/memory.py`, `routers/reflect.py`, `routers/todo.py`, `routers/files.py`) mounted on the app. Pure refactor, no behavior change — do it **after** the P0 auth work and **with** the M1 tests in place so the split is verifiable. **Model: Opus 4.8** to plan the seams; **Sonnet 5** to execute per-router moves.

### M4 — Stray junk directories & scratchpad duplication

**Observed at repo root:** `--help/` (literally contains captured `ls --help` output — created by a malformed redirect), `append/memory/` and `check/memory/` (accidental relative-path writes), and **two** scratch areas: `scratch pad/` (with a space, now gitignored after the MFA-QR/password incident) and `scratchpad/`.

**Why it matters:** Low severity but these are exactly the kind of cruft that (a) confuses `find`/greps and tooling, (b) previously leaked a live secret (`scratch pad/`), and (c) signals loose shell hygiene that produced them.

**What/how:** Delete `--help/`, `append/`, `check/` (verify they contain nothing real first — they don't). Consolidate to a single scratch directory; keep the space-free `scratchpad/`, remove `scratch pad/` after confirming nothing references it. Confirm both are gitignored (`scratch pad/` and `scratchpad/` both are). **Confirm with Nick before deleting**, per the destructive-action policy — but these are safe removals. **Model: Haiku 4.5.**

---

## 5. Opportunities (P2–P3) — capability & robustness upgrades

### O1 — NERO loop observability and guardrails

**Current state:** `reflect.py` (831 lines) runs a local-Ollama gate (`mistral:latest`) → writer (`mistral-small:latest`) after each turn, proposing memory/skill edits to `memory/nero_inbox.md`; `insights.py` surfaces gate hit-rate. There's a documented **auto-mode pitfall** (`feedback_reflection_loop_auto_mode`).

**Opportunity:** Add a small metrics log (proposals generated / applied / rejected, gate pass rate, model latency) and a weekly digest so the loop's *quality* is measurable, not just its activity. Add a hard cap on proposals/day and a diff-size ceiling per proposal (mirroring the `guard_memory_write` philosophy) so auto-mode can never make large unreviewed edits. **Worth it:** Yes, medium — it turns a black-box self-modifier into an auditable one, directly serving your "reliability/auditable >> clever" principle. **Model:** Opus 4.8 to design the guardrails (self-modification safety); local Ollama continues to run the loop itself.

### O2 — Consolidate health/self-healing into one supervisor

**Current state:** `service_monitor.py`, `verify_backup_health.py`, `sync_and_score.py`, `.backup_health`, plus the voice-box auto-restart in `startup.py` — health logic is spread across several scripts and the startup hook.

**Opportunity:** A single `lucent-health` systemd timer that checks every declared service (from one source-of-truth registry: name, port, expected bind, restart command), self-heals by PID/port (respecting `feedback_never_broad_process_kill`), and writes one health JSON the UI already knows how to read (`/services/health`). **Worth it:** Medium — reduces the "is it up?" ambiguity from R3 and removes duplicated health code. **Model:** Sonnet 5.

### O3 — Recall index: incremental / on-disk vector store

**Current state:** `.recall_index.json` is a 15 MB JSON the recall path loads; it's rebuilt when sources change (`memory_index.py`). This is the root cause of R1's repo bloat and means each recall may load/parse a large file.

**Opportunity:** Move to an incremental, on-disk vector store (sqlite-vec, or a small FAISS/Chroma file) that updates only changed chunks instead of rewriting a monolithic JSON, and is inherently git-ignored as a derived DB. **Worth it:** Medium, and it compounds with R1 — but sequence it *after* R1's quick gitignore fix, which captures 90% of the benefit for 10% of the effort. **Model:** Opus 4.8 to choose/validate the store (embedding-pipeline correctness); Sonnet 5 to implement.

---

## 6. Consolidated Roadmap (dependency-ordered)

| Phase | Work | Blocks / depends on | Recommended model |
|-------|------|---------------------|-------------------|
| **0 — Close the tunnel-reachable chain (now)** | **S2 (proxy session enforcement) + S3 (backend auth + `/view-file` allowlist)** + the S2/S3 security tests from M1 | none — this is the live exposure | **Opus 4.8** + Sonnet 5 (tests) |
| **1 — Cheap hardening (bundle with, or right after, Phase 0)** | S1 (bind localhost) + S4 (CORS allowlist) + R1 Phase A (gitignore index) | none | Opus 4.8 (S1/S4), Haiku (R1a) |
| **2 — Harden & isolate** | S5 (argon2/cookies/rate-limit) + ~~R2 (venv+pin)~~ ✅ done + R3 (ownership/supervision) | Phase 0 | Sonnet 5 |
| **3 — Safety net** | ~~M1 memory-integrity + hook tests, CI wiring~~ ✅ done | Phase 1 (reuses its tests) | Sonnet 5, Opus for test design |
| **4 — Reclaim & clean** | R1 Phase B (history rewrite, **with backup + Nick OK**) + M2 (dead code) + M4 (junk dirs) | Phase 3 (tests protect the cleanup) | Sonnet 5 / Haiku |
| **5 — Restructure** | M3 (`server.py` → routers) | Phase 3 (tests) | Opus plan / Sonnet exec |
| **6 — Elevate** | O1 (NERO guardrails), O2 (health supervisor), O3 (vector store) | Phases 2–4 | Opus design / Sonnet+local Ollama |

**Guiding sequence rule:** contain exposure → close bypasses → add the test net → *then* refactor/clean behind the net. Never do the history rewrite (R1b) or the big refactor (M3) before the tests (M1) exist to catch regressions.

---

## 7. Documentation corrections noted during the audit

- `lucent-init.sh:104` says `enforce_unsummarized_sessions.py` "was REMOVED" — it is still present in `scripts/`. Either delete the file or fix the comment (M2).
- `auth_proxy.py` comments ("*auth is handled at the proxy level*") assert a guarantee the code doesn't provide (S2) — remove/correct so the docs stop vouching for a control that isn't there.
- `CLAUDE.md` / architecture docs describe the 8001-local / 8002-MFA split as if enforced; until S1–S3 land, that description is aspirational. Update once fixed, or annotate as "target state."
- `hash_password` docstring ("*Use bcrypt or argon2 in production*") acknowledges the gap but the code still ships SHA-256 (S5).

---

## 8. Open questions for Nick (would sharpen prioritization)

1. **Confirm the tunnel exposes only 8002** (you've stated the host is isolated + only the MFA UI is tunneled — this Q is just to *assert* it in config, since the entire S2/S3 severity call rests on 8002 being the one reachable port). I can inspect `scratchpad/LucentTailSetup.ps1` and the tailscale ACL to verify no 8001/other forward exists.
2. **Threat model:** Single isolated user forever, or do you intend to ever share the UI or widen access? That's the difference between S5/CORS being "nice hardening" and "required."
3. **Go-ahead on Phase 0:** Want me to start closing the S2→S3 chain now (proxy session enforcement + `/view-file` allowlist + backend-behind-proxy check), with the security regression tests written alongside? I'd do it on a branch and show you the diff before restarting anything. The cheap hardening (S1 bind, S4 CORS, gitignore the index) can ride along in the same branch.
```
