import { tool } from "@opencode-ai/plugin"
import path from "path"

export const check = tool({
  description: "MANDATORY STARTUP RITUAL CHECK. Call this tool BEFORE generating any text response to the user. Verifies if the startup ritual needs to be executed. Returns 'RITUAL OK' or 'RITUAL NEEDED' with instructions. Do not skip this tool.",
  args: {},
  async execute(args, context) {
    const script = path.join(context.worktree, "scripts", "verify_startup.py")
    try {
      const result = await Bun.$`python3 ${script} check`.text()
      return result.trim()
    } catch (e: any) {
      // Exit code 1 means ritual needed — still return the output
      return e.stdout?.trim() || e.stderr?.trim() || "RITUAL NEEDED"
    }
  },
})

export const markComplete = tool({
  description: "Mark the startup ritual as complete. Call this after executing all ritual steps (context loading, compression, voice box check, session logging).",
  args: {},
  async execute(args, context) {
    const script = path.join(context.worktree, "scripts", "verify_startup.py")
    try {
      const result = await Bun.$`python3 ${script} mark-complete`.text()
      return result.trim()
    } catch (e: any) {
      return e.stdout?.trim() || e.stderr?.trim() || "Failed to mark ritual complete"
    }
  },
})
