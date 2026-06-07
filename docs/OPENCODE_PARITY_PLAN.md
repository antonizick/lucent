# OpenCode → Claude Code Parity Plan for Lucent

**Created:** 2026-06-07
**Status:** ✅ COMPLETE — all 4 phases implemented and verified 2026-06-07
**Goal:** Make Lucent operate as effectively and reliably under OpenCode as under Claude Code, in a product-agnostic way.

---

## Background / Verdict

OpenCode **is** a viable host for Lucent — the platform is fully capable of parity. The current
integration is not yet an equal: it's a thin, pre-NERO shim (last touched ~2026-05-13) that relies on
the model *voluntarily* calling a `lucent_startup` tool and omits the entire NERO self-improvement layer.

**Headline finding:** `docs/STARTUP_ARCHITECTURE.md` justified the voluntary-tool design by claiming
"OpenCode does not have a UserPromptSubmit-equivalent hook." **That premise is now false.** The installed
`@opencode-ai/plugin` (v1.14.50) exposes automatic, platform-level hooks that map ~1:1 to Claude Code's:

| Claude Code hook | OpenCode hook (available, **currently unused**) |
|---|---|
| `SessionStart` | `event` (session lifecycle) / first `chat.message` |
| `UserPromptSubmit` | **`chat.message`** + `experimental.chat.system.transform` |
| `Stop` | `event` (session idle) / `experimental.text.complete` |
| `PreCompact` | **`experimental.session.compacting`** (direct equivalent) |
| `SessionEnd` | `event` |

The gap is implementation debt, not a platform limitation.

---

## Design Principle: Single-Source Logic

All hook logic already exists as Python in `scripts/` (`startup.py`, `lucent-init.sh`, `reflect.py`,
`pre_compact.py`, `log_session_end.py`). The OpenCode plugin should **call those same scripts**, not
reimplement them in TypeScript. This keeps both platforms behaviorally identical and prevents logic forks.
Phase 4 makes those scripts fully platform-agnostic so neither platform has special-cased branches.

All `experimental.*` hooks must have **graceful no-op fallbacks** (same pattern as the existing
Ollama-unavailable handling) so an OpenCode upgrade can never silently break Lucent.

---

## Phases, with Optimal Model per Phase

| Phase | Scope | **Optimal model** | Why this model |
|---|---|---|---|
| **1. Rewrite plugin around automatic hooks** | Replace voluntary `lucent_startup` with a `chat.message` hook (per-turn injection via `lucent-init.sh`); add once-per-session guard running `startup.py` on first message; keep `lucent_startup` as manual recovery fallback. | **Opus 4.8** | Novel architecture, subtle correctness (session-once guard, hook timing/ordering, experimental-API behavior), highest blast radius. Heavy-judgment work per the model-selection criterion. |
| **2. Port NERO into OpenCode lifecycle** | `event`/`experimental.text.complete` → fire `reflect.py` after responses; wire `experimental.session.compacting` → `pre_compact.py`; confirm per-turn recall/proposals flow through Phase 1's injection. | **Sonnet 4.6** | Well-scoped wiring that follows the pattern established in Phase 1. Escalate the compaction-hook piece to Opus only if its semantics prove tricky. |
| **3. Validation parity & voice enforcement** | Run the same startup validation gates (compression, unsummarized sessions, LTMemory completeness) and surface blocking states; soft-enforce the three-layer voice rule via a post-response check. | **Sonnet 4.6** | Reuses existing gate logic; mostly wiring + straightforward enforcement. |
| **4. Single-source refactor + docs** | Make hook scripts platform-agnostic (env-detect, no Claude-only assumptions) so both platforms call the same Python; rewrite `STARTUP_ARCHITECTURE.md` (correct the false premise) and `AGENTS.md`. | **Sonnet 4.6** for the refactor; **Haiku 4.5** acceptable for the pure prose/doc pass | Refactor needs moderate care (don't break Claude Code path); doc prose is mechanical once the refactor is known. |

**Model-selection rule of thumb** (from standing preference): Opus for heavy judgment / novel
architecture / high blast radius; Sonnet for well-scoped implementation on an established pattern;
Haiku for trivial/mechanical work. Default Sonnet unless significant reasoning is required.

---

## Phase Detail

### Phase 1 — Rewrite plugin around automatic hooks (Opus 4.8)
- In `.opencode/lucent-plugin.ts`, implement `chat.message` hook → shell out to `scripts/lucent-init.sh`,
  inject its output (date, RULES ACTIVE, NERO semantic recall, reminders, priority email, daily-note tail,
  proposals count) into the turn.
- Add a per-session guard (e.g. marker keyed by `sessionID`) so the first message also runs `startup.py`
  (identity bundle + validation gates), subsequent messages don't.
- Retain `lucent_startup` tool as the documented manual recovery path.
- **Why first / highest leverage:** this is where the reliability gap actually lives — it removes the
  model-discretion failure mode entirely.

### Phase 2 — Port NERO into OpenCode lifecycle (Sonnet 4.6)
- Hook `event` (session-idle) or `experimental.text.complete` → run `reflect.py` (detached, as on Claude Code).
- Hook `experimental.session.compacting` → run `pre_compact.py`, append its output to the compaction `context[]`.
- Verify recall + proposals surface through Phase 1's per-turn injection (no separate work needed).

### Phase 3 — Validation parity & voice enforcement (Sonnet 4.6)
- Ensure Phase 1's startup path runs the same validation gates and surfaces blocking states to the model.
- Add a soft post-response check (via `experimental.text.complete`) that the voice box was hit; warn if not.

### Phase 4 — Single-source refactor + docs (Sonnet 4.6 / Haiku 4.5 for prose)
- Refactor `scripts/*` so platform detection is automatic; no Claude-only assumptions.
- Rewrite `docs/STARTUP_ARCHITECTURE.md` (correct the outdated premise; document the hook-based OpenCode design).
- Update `AGENTS.md` to reflect automatic hooks rather than the voluntary-tool directive.

---

## Effort Notes
- Phase 1 is the bulk of the reliability win and is roughly one focused session; the Python is reusable,
  so it's mostly TypeScript plumbing.
- Phases 2–3 build directly on Phase 1's pattern.
- Phase 4 is cleanup + documentation.

## Risk / Caveat
Several target hooks are `experimental.*` in the SDK — stable enough to use, but every one must degrade to a
no-op if absent or changed, so OpenCode upgrades can't silently break Lucent.
