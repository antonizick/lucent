/**
 * Lucent OpenCode Plugin
 *
 * Purpose: Enforce the Lucent startup ritual at the platform level by registering
 * a tool in OpenCode's schema. Tool-schema entries are binding — the model treats
 * a named tool differently from a text instruction. This is why this mechanism
 * exists: text instructions in AGENTS.md are passive; a tool in the schema is not.
 *
 * See docs/STARTUP_ARCHITECTURE.md for full design rationale and failure history.
 */

import { tool } from "@opencode-ai/plugin"
import type { Plugin } from "@opencode-ai/plugin"

export const server: Plugin = async (input) => {
  const { $, directory } = input

  return {
    tool: {
      /**
       * lucent_startup
       *
       * The startup ritual enforcement tool. Every time a new OpenCode session
       * begins, the model should call this before generating any text response.
       *
       * What it does:
       *   1. Runs startup-helper.py → verifies voice box is online, initializes session logger
       *   2. Reads today's daily note → injects live session context into the conversation
       *   3. Returns a protocol reminder → ensures three-layer requirement is active
       *
       * The tool description below is written to be recognized as mandatory by the
       * model's tool-use reasoning. The word "MANDATORY" and the phrase "before your
       * first response" are the enforcement hooks.
       */
      lucent_startup: tool({
        description:
          "MANDATORY: Call this tool BEFORE generating your first response in any session. " +
          "This is the Lucent session initializer. It checks voice box status, starts session " +
          "logging, and returns today's active work context (daily note). Without calling this, " +
          "you are operating without live context and will behave generically instead of as Lucent. " +
          "Nick expects this to be called automatically at session start. " +
          "If Nick says 'lucent init', 'run startup', or 'run your startup ritual', call this tool.",

        args: {},

        async execute(_args, _ctx) {
          const today = new Date().toISOString().split("T")[0] // YYYY-MM-DD

          // ── Step 1: Startup helper ────────────────────────────────────────────────
          // Runs startup-helper.py which:
          //   - Checks voice box health at localhost:8001/services/health
          //   - Calls session_logger.py init to create today's daily note header
          // nothrow() prevents exceptions on non-zero exit — we handle errors manually.
          let helperStatus = ""
          try {
            const result = await $`python3 ${directory}/.opencode/startup-helper.py`
              .nothrow()
              .quiet()
            helperStatus = result.text().trim()
          } catch (e) {
            helperStatus = `WARNING: startup-helper.py failed — ${String(e)}`
          }

          // ── Step 2: Today's daily note ────────────────────────────────────────────
          // The daily note is NOT in opencode.json instructions (it's dynamic — a new
          // file each day). This tool injects it into the conversation at startup.
          // We take the last 3000 chars to capture the most recent activity without
          // flooding the context with an entire day's history.
          let dailyNote = "(no daily note exists for today yet — this is the first session of the day)"
          let noteLength = 0
          try {
            const result = await $`cat ${directory}/memory/${today}.md`
              .nothrow()
              .quiet()
            if (result.exitCode === 0) {
              const raw = result.text()
              noteLength = raw.length
              dailyNote =
                raw.length > 3000
                  ? `[truncated — showing most recent 3000 chars of ${raw.length} total]\n...\n${raw.slice(-3000)}`
                  : raw
            }
          } catch { /* file not found is expected on a fresh day */ }

          // ── Step 3: Yesterday's note (if today's is sparse) ─────────────────────
          // If today's note has fewer than 200 chars, the session just started and
          // there's little context yet. Pull in yesterday's compressed note for continuity.
          let recentContext = ""
          if (noteLength < 200) {
            try {
              const yesterday = new Date(Date.now() - 86_400_000).toISOString().split("T")[0]
              const result = await $`cat ${directory}/memory/${yesterday}.md`
                .nothrow()
                .quiet()
              if (result.exitCode === 0) {
                const raw = result.text()
                recentContext =
                  `\n── YESTERDAY (${yesterday}) ─────────────────────────────────────\n` +
                  (raw.length > 1500 ? raw.slice(-1500) : raw)
              }
            } catch {}
          }

          // ── Assemble return value ─────────────────────────────────────────────────
          // This string becomes part of the tool result the model sees. Everything
          // above the protocol reminder is context. The protocol reminder is the
          // re-assertion of three-layer compliance for this session.
          return [
            "╔══════════════════════════════════════════╗",
            "║        LUCENT SESSION INITIALIZED         ║",
            "╚══════════════════════════════════════════╝",
            "",
            "STARTUP STATUS:",
            helperStatus || "(startup-helper produced no output)",
            "",
            `TODAY'S CONTEXT (${today}):`,
            dailyNote,
            recentContext,
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "THREE-LAYER PROTOCOL — EVERY RESPONSE:",
            "  1. VOICE:  curl -X POST http://localhost:8001/speak \\",
            `             -H 'Content-Type: application/json' \\`,
            `             -d '{"text": "your message"}'`,
            `  2. LOG:    append to memory/${today}.md`,
            "  3. TEXT:   your response in Claude Code",
            "Send voice FIRST, then text. No exceptions.",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
          ].join("\n")
        },
      }),
    },
  }
}
