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

          // ── Step 2: Daily notes (today + 2 previous days) ────────────────────────
          // Daily notes are NOT in opencode.json instructions — they're dynamic (a new
          // file each day). This tool injects them at startup to provide session continuity.
          //
          // Loading strategy:
          //   Today:         last 3000 chars — most detail, current in-progress work
          //   Yesterday:     last 1500 chars — recent context; already Curator-compressed
          //   Two days ago:  last 1000 chars — background context; already compressed
          //
          // Previous notes are compressed to 1–2 paragraphs by Curator at each session
          // start, so token cost is low. This mirrors Claude Code's 7-day window
          // but scoped to 3 days to avoid excessive context in the tool return value.

          const readNote = async (date: string, maxChars: number): Promise<string | null> => {
            try {
              const result = await $`cat ${directory}/memory/${date}.md`.nothrow().quiet()
              if (result.exitCode !== 0) return null
              const raw = result.text()
              return raw.length > maxChars
                ? `[truncated — showing most recent ${maxChars} of ${raw.length} chars]\n...\n${raw.slice(-maxChars)}`
                : raw
            } catch {
              return null
            }
          }

          const yesterday   = new Date(Date.now() - 86_400_000).toISOString().split("T")[0]
          const twoDaysAgo  = new Date(Date.now() - 172_800_000).toISOString().split("T")[0]

          const todayNote      = await readNote(today,      3000)
          const yesterdayNote  = await readNote(yesterday,  1500)
          const twoDaysAgoNote = await readNote(twoDaysAgo, 1000)

          const dailyNote = todayNote ?? "(no daily note exists for today yet — this is the first session of the day)"

          const recentContext = [
            yesterdayNote  ? `\n── YESTERDAY (${yesterday}) ──────────────────────────────────────\n${yesterdayNote}`  : "",
            twoDaysAgoNote ? `\n── TWO DAYS AGO (${twoDaysAgo}) ──────────────────────────────────\n${twoDaysAgoNote}` : "",
          ].join("")

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
