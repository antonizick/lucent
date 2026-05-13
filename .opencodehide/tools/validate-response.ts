import { tool } from "@opencode-ai/plugin"
import path from "path"

export const validateResponse = tool({
  description: "MANDATORY RESPONSE VALIDATION. Call this tool BEFORE sending any text response to the user. Validates that all three layers are present: daily note entry, voice message, and text response. Do not generate text output until this tool returns OK_TO_SEND.",
  args: {
    dailyNoteEntry: {
      type: "string",
      description: "The entry to append to today's daily note (e.g., '## [HH:MM] Task description')"
    },
    voiceMessage: {
      type: "string",
      description: "The message text to send to the voice box"
    },
    textResponse: {
      type: "string",
      description: "The text response to send to the user"
    }
  },
  async execute(args, context) {
    const script = path.join(context.worktree, "scripts", "validate_response.py")
    try {
      const result = await Bun.$`python3 ${script} ${args.dailyNoteEntry} ${args.voiceMessage} ${args.textResponse}`.json()
      return JSON.stringify(result, null, 2)
    } catch (e: any) {
      // Parse output even on non-zero exit
      try {
        const output = e.stdout?.trim() || e.stderr?.trim() || ""
        if (output) {
          return output
        }
      } catch {}
      return JSON.stringify({
        status: "ERROR",
        message: "Validation script failed. Check response components."
      })
    }
  },
})
