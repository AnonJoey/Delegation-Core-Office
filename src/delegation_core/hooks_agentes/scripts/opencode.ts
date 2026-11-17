// delegation-core OpenCode plugin. OpenCode only loads TypeScript plugins, so
// this is a shim: the decision lives in Python (`delegation-core rewrite`, exit
// 3 = rewritten, 1 = leave it). Ported from RTK's hooks/opencode/rtk.ts.
import type { Plugin } from "@opencode-ai/plugin"

export const DelegationCoreOpenCodePlugin: Plugin = async ({ $ }) => {
  try {
    await $`which delegation-core`.quiet()
  } catch {
    return {}
  }
  return {
    "tool.execute.before": async (input, output) => {
      const tool = String(input?.tool ?? "").toLowerCase()
      if (tool !== "bash" && tool !== "shell") return
      const args = output?.args as Record<string, unknown> | undefined
      const command = args?.command
      if (typeof command !== "string" || !command) return
      const r = await $`delegation-core rewrite ${command}`.quiet().nothrow()
      const rewritten = String(r.stdout).trim()
      if (r.exitCode === 3 && rewritten && rewritten !== command) args!.command = rewritten
    },
  }
}
