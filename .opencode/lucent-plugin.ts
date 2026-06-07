/**
 * Lucent OpenCode Plugin — Automatic Hook Architecture (Phase 1)
 *
 * PURPOSE
 * -------
 * Bring OpenCode to parity with Claude Code's hook-driven Lucent runtime.
 *
 * Claude Code fires Lucent's logic automatically at the platform level via
 * settings.json hooks (SessionStart, UserPromptSubmit, …). The OpenCode plugin
 * SDK (v1.14.x) exposes equivalent automatic hooks — this plugin wires them up:
 *
 *   Claude Code hook   →  OpenCode hook (used here)
 *   ------------------    ----------------------------------------
 *   SessionStart       →  first `chat.message` of a session (startup guard)
 *   UserPromptSubmit   →  every `chat.message` (per-turn context injection)
 *
 * SINGLE-SOURCE PRINCIPLE
 * -----------------------
 * This plugin does NOT reimplement Lucent logic. It shells out to the exact same
 * Python/bash that Claude Code's hooks run:
 *   - scripts/startup.py     → identity bundle + validation gates  (once per session)
 *   - scripts/lucent-init.sh → dynamic per-turn state              (every message)
 * Behaviour stays identical across both platforms; there is no logic fork.
 *
 * RELIABILITY
 * -----------
 * Every hook is wrapped so a failure can never break a turn. If a script errors,
 * the turn proceeds without injection (degraded, never broken) — mirroring the
 * "purely additive" contract of the underlying scripts.
 *
 * The historical voluntary `lucent_startup` tool is RETAINED as a manual recovery
 * path (force re-run), but is no longer the primary enforcement mechanism — the
 * `chat.message` hook now fires automatically, removing the model-discretion
 * failure mode documented in docs/STARTUP_ARCHITECTURE.md.
 *
 * See docs/OPENCODE_PARITY_PLAN.md for the full plan.
 */

import { tool } from "@opencode-ai/plugin"
import type { Plugin } from "@opencode-ai/plugin"

const FALLBACK_ROOT = "/home/nick/dev/lucent"

// Sessions whose startup ritual has already run this process lifetime.
// Backed up by a /tmp marker so it also survives plugin reloads within a session.
const startedSessions = new Set<string>()

export const server: Plugin = async (input) => {
  const { $, directory } = input
  const root = directory || FALLBACK_ROOT

  // ── Run the heavy startup ritual (startup.py) at most once per session ──────
  // Returns the identity bundle (stdout) on the first call for a session; "" after.
  // `force` bypasses the guard (used by the manual recovery tool).
  async function runStartup(sessionID: string, force = false): Promise<string> {
    const marker = `/tmp/lucent_oc_session_${sessionID}`

    if (!force) {
      if (startedSessions.has(sessionID)) return ""
      const exists = await $`test -f ${marker}`.nothrow().quiet()
      if (exists.exitCode === 0) {
        startedSessions.add(sessionID)
        return ""
      }
    }

    let bundle = ""
    try {
      const r = await $`python3 ${root}/scripts/startup.py`.nothrow().quiet()
      bundle = r.text().trim()
    } catch (e) {
      bundle = `[Lucent] WARNING: startup.py failed — ${String(e)}`
    }

    await $`touch ${marker}`.nothrow().quiet()
    startedSessions.add(sessionID)
    return bundle
  }

  // ── Run the per-turn dynamic hook (lucent-init.sh) ─────────────────────────
  // Feeds the user's message text on stdin as {"prompt": "..."} so the script's
  // semantic-recall step (memory_recall.py) can find relevant memories.
  async function runPerTurn(userText: string): Promise<string> {
    try {
      const payload = JSON.stringify({ prompt: userText })
      const r = await $`echo ${payload} | bash ${root}/scripts/lucent-init.sh`
        .nothrow()
        .quiet()
      return r.text().trim()
    } catch (e) {
      return `[Lucent] WARNING: lucent-init.sh failed — ${String(e)}`
    }
  }

  // ── Pull the user's typed text out of the incoming message parts ───────────
  function extractUserText(parts: any[]): string {
    return (parts || [])
      .filter((p) => p?.type === "text" && typeof p.text === "string" && !p.synthetic)
      .map((p) => p.text)
      .join("\n")
  }

  // ── Reflection (Stop-hook equivalent) ──────────────────────────────────────
  //
  // Claude Code's Stop hook pipes `{"transcript_path": "<jsonl file>"}` to
  // `reflect.py`, which parses Claude-Code-shaped JSONL — lines of
  // `{"type": "user"|"assistant", "message": {"content": "..."}, "uuid": "..."}`
  // — to extract the last exchange (see extract_last_exchange in reflect.py).
  //
  // OpenCode stores sessions in its own format, reachable via the SDK
  // (`client.session.messages`), not as Claude-Code JSONL. Rather than fork
  // reflect.py's gate/writer/proposal logic — the actual "single source" that
  // matters — this is a thin TRANSLATION SHIM: it re-shapes OpenCode's message
  // history into the exact JSONL reflect.py already knows how to read, then
  // invokes reflect.py exactly as Claude Code does (same stdin contract, same
  // hook_entry(), same detached worker, same dedup-by-uuid). Zero logic fork.
  const reflectedSessions = new Set<string>()

  async function buildClaudeShapedTranscript(sessionID: string): Promise<string | null> {
    try {
      const res: any = await (input.client as any).session.messages({ path: { id: sessionID } })
      const entries: any[] = res?.data || []
      if (!entries.length) return null

      const lines = entries.map((e) => {
        const role = e?.info?.role === "assistant" ? "assistant" : "user"
        const text = (e?.parts || [])
          .filter((p: any) => p?.type === "text" && typeof p.text === "string" && !p.synthetic)
          .map((p: any) => p.text)
          .join("\n")
        return JSON.stringify({
          type: role,
          message: { role, content: text },
          uuid: e?.info?.id || "",
        })
      })

      const tmpPath = `/tmp/lucent_oc_transcript_${sessionID}.jsonl`
      const { writeFile } = await import("node:fs/promises")
      await writeFile(tmpPath, lines.join("\n") + "\n", "utf8")
      return tmpPath
    } catch {
      return null
    }
  }

  async function triggerReflection(sessionID: string): Promise<void> {
    try {
      const transcriptPath = await buildClaudeShapedTranscript(sessionID)
      if (!transcriptPath) return

      const payload = JSON.stringify({ transcript_path: transcriptPath })
      // Same stdin contract as Claude Code's Stop hook → hook_entry() →
      // spawns reflect.py's detached Haiku-gate/Sonnet-writer worker.
      await $`echo ${payload} | python3 ${root}/scripts/reflect.py`.nothrow().quiet()
    } catch {
      // Reflection is purely additive — never let it affect the session.
    }
  }

  // ── PostToolUse(Read) equivalent — skill usage tracking ───────────────────
  //
  // Claude Code's Insights "Top used" skill stats come from skills.py's
  // bump_use(), which historically only fired through the `skills.py view`
  // CLI path — but CLAUDE.md documents loading skill bodies by reading
  // memory/skills/<slug>/SKILL.md directly with the Read tool, bypassing the
  // counter entirely. scripts/skill_read_tracker.py closes that gap on the
  // Claude Code side via a PostToolUse(Read) hook; `tool.execute.after` is
  // OpenCode's equivalent. Same single-source principle: shell out to the
  // identical script with the identical stdin JSON contract so both platforms
  // feed one counter, one definition of "used".
  async function trackSkillRead(toolName: string, args: any): Promise<void> {
    try {
      if (!/^read$/i.test(toolName || "")) return
      const filePath = args?.filePath || args?.file_path || args?.path || ""
      if (!/memory\/skills\/[^/]+\/SKILL\.md$/.test(String(filePath))) return

      const payload = JSON.stringify({ tool_name: "Read", tool_input: { file_path: filePath } })
      await $`echo ${payload} | python3 ${root}/scripts/skill_read_tracker.py`.nothrow().quiet()
    } catch {
      // Tracking is purely additive — never let it affect a tool call.
    }
  }

  // ── Soft voice-box enforcement (Stop-hook "did Lucent speak?" backstop) ────
  //
  // Claude Code's voice rule is enforced by convention (CLAUDE.md), not by a
  // blocking script — `validate_response.py` exists but isn't wired into any
  // hook. The closest thing to a real signal is the activity log: every
  // successful POST to /speak is appended there as a `[voice_box]` line with
  // an ISO timestamp (see ui/server.py's `log_activity` call in the /speak
  // handler). This check mirrors that same evidence source: record when the
  // turn started, then at text-completion time look for a `[voice_box]` line
  // timestamped after that moment. Soft — it only appends a warning, never
  // blocks, and fails open (assumes compliant) if the log can't be read.
  const turnStartedAt = new Map<string, number>()
  const warnedMessages = new Set<string>()

  async function voiceBoxHitSince(sinceMs: number): Promise<boolean> {
    try {
      const today = new Date().toISOString().slice(0, 10)
      const logPath = `${root}/ui/logs/activity_${today}.log`
      const r = await $`grep -F '[voice_box]' ${logPath}`.nothrow().quiet()
      const lines = r.text().trim().split("\n").filter(Boolean)
      for (let i = lines.length - 1; i >= 0; i--) {
        const m = lines[i].match(/^\[(\d{4}-\d{2}-\d{2}T[\d:.]+)\]/)
        if (m) {
          const t = new Date(m[1]).getTime()
          if (!Number.isNaN(t) && t >= sinceMs) return true
        }
      }
      return false
    } catch {
      return true // fail open — never warn off a check we couldn't run
    }
  }

  // ── PreCompact equivalent ──────────────────────────────────────────────────
  // Direct port: pre_compact.py prints a "must-keep" block to stdout; Claude
  // Code injects that into the compaction prompt. `experimental.session.compacting`
  // is OpenCode's documented direct equivalent — same idea, append to context[].
  async function runPreCompactGuard(): Promise<string> {
    try {
      const r = await $`python3 ${root}/scripts/pre_compact.py`.nothrow().quiet()
      return r.text().trim()
    } catch {
      return ""
    }
  }

  return {
    /**
     * UserPromptSubmit equivalent — fires automatically on every user message.
     * Injects (a) the startup bundle on the first message of a session, and
     * (b) the per-turn dynamic state on every message, as a synthetic text part.
     */
    "chat.message": async (_input, output) => {
      try {
        const sessionID = output.message.sessionID
        const userText = extractUserText(output.parts)

        // Mark when this turn began — the soft voice-box check (below,
        // experimental.text.complete) uses this as its "since" boundary.
        turnStartedAt.set(sessionID, Date.now())

        // SEQUENTIAL, not parallel — mirrors Claude Code's guarantee that
        // SessionStart (startup.py) fully completes — including writing the
        // `.startup_ready_<date>.txt` marker — before the first
        // UserPromptSubmit (lucent-init.sh) ever runs. Racing them would let
        // lucent-init.sh check for the marker before startup.py writes it,
        // delaying the voice acknowledgment by a full turn on session start.
        // (On later turns runStartup() short-circuits via the guard, so the
        // sequencing costs nothing in practice.)
        const bundle = await runStartup(sessionID)
        const perTurn = await runPerTurn(userText)

        const injected = [bundle, perTurn].filter((s) => s && s.length).join("\n\n")
        if (!injected.trim()) return

        output.parts.push({
          id: `lucent-ctx-${Date.now()}`,
          sessionID: output.message.sessionID,
          messageID: output.message.id,
          type: "text",
          text: `<lucent-context>\n${injected}\n</lucent-context>`,
          synthetic: true,
        } as any)
      } catch {
        // Never break a turn — a failed injection degrades silently.
      }
    },

    /**
     * Stop equivalent — fires on platform lifecycle events. We use
     * `session.idle` (the assistant has finished responding and the session
     * has gone quiet) as the trigger for NERO reflection, mirroring Claude
     * Code's Stop → reflect.py wiring. Dedup against re-firing for the same
     * idle moment is handled by reflect.py itself (last_leaf_uuid in state),
     * so it's safe to call on every idle event.
     */
    /**
     * Soft Stop-equivalent backstop — fires as each assistant text part
     * finishes streaming. Mirrors Claude Code's (convention-based) three-layer
     * voice rule: if no `[voice_box]` activity-log entry shows up after the
     * turn started, append a gentle on-screen reminder. Never blocks the
     * response — purely a visible nudge, deduped per messageID so a
     * multi-part response doesn't repeat the warning.
     */
    "experimental.text.complete": async (input, output) => {
      try {
        const { sessionID, messageID } = input
        if (warnedMessages.has(messageID)) return
        const startedAt = turnStartedAt.get(sessionID)
        if (startedAt == null) return

        const hit = await voiceBoxHitSince(startedAt)
        if (!hit) {
          warnedMessages.add(messageID)
          output.text =
            output.text +
            "\n\n[Lucent] ⚠ Voice box not detected for this response — " +
            "the three-layer rule (voice + daily note + text) requires it. " +
            "Send the /speak call before finishing."
        } else {
          warnedMessages.add(messageID)
        }
      } catch {
        // Enforcement must never break a turn.
      }
    },

    /**
     * PostToolUse(Read) equivalent — fires after every tool call completes.
     * We only care about Read calls that loaded a SKILL.md; trackSkillRead
     * filters and shells out to the same script Claude Code's hook uses.
     */
    "tool.execute.after": async (input) => {
      void trackSkillRead(input.tool, input.args)
    },

    event: async ({ event }) => {
      try {
        if (event?.type === "session.idle") {
          const sessionID = (event as any)?.properties?.sessionID
          if (sessionID) {
            // Fire-and-forget — never let reflection block the session.
            void triggerReflection(sessionID)
          }
        }
      } catch {
        // Reflection must never affect the session.
      }
    },

    /**
     * PreCompact equivalent — fires before OpenCode compacts the session.
     * Runs the same memory-durability guard Claude Code runs and appends its
     * "must-keep" block to the compaction context, exactly like
     * Claude Code injects pre_compact.py's stdout into the compaction prompt.
     */
    "experimental.session.compacting": async (_input, output) => {
      try {
        const guard = await runPreCompactGuard()
        if (guard) {
          output.context = [...(output.context || []), guard]
        }
      } catch {
        // Compaction must never be blocked by the guard.
      }
    },

    tool: {
      /**
       * lucent_startup — MANUAL RECOVERY ONLY.
       *
       * The `chat.message` hook now runs startup automatically, so this tool is
       * no longer required for normal operation. It remains as the deliberate
       * recovery mechanism: if a session ever looks "generic" (no Lucent context),
       * Nick can say "run your lucent_startup tool" to force a full re-init.
       */
      lucent_startup: tool({
        description:
          "MANUAL RECOVERY: Force a full Lucent re-initialization for this session. " +
          "Startup normally runs automatically on the first message — call this only " +
          "if the session appears to be missing Lucent context (no voice, generic " +
          "behavior). Runs startup.py (identity bundle + validation gates) and returns " +
          "today's dynamic context. Trigger phrases: 'lucent init', 'run startup', " +
          "'run your lucent_startup tool'.",

        args: {},

        async execute(_args, ctx) {
          const sessionID = (ctx as any)?.sessionID || "manual"
          // Sequential — same ordering guarantee as the chat.message hook
          // (startup.py must finish writing its readiness marker before
          // lucent-init.sh checks for it).
          const bundle = await runStartup(sessionID, true)
          const perTurn = await runPerTurn("")
          return [
            "╔══════════════════════════════════════════╗",
            "║   LUCENT SESSION RE-INITIALIZED (manual)  ║",
            "╚══════════════════════════════════════════╝",
            "",
            bundle || "(startup.py produced no output)",
            "",
            perTurn || "(lucent-init.sh produced no output)",
          ].join("\n")
        },
      }),
    },
  }
}
