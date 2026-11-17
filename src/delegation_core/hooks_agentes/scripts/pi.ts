// delegation-core Pi extension. Pi only loads TypeScript extensions, so this is
// a shim over the Python decision (`delegation-core rewrite`). Ported from RTK's
// hooks/pi/rtk.ts.
import type { ExtensionAPI, ToolCallEvent } from "@earendil-works/pi-coding-agent"

export default async function (pi: ExtensionAPI) {
  const probe = await pi.exec("delegation-core", ["--help"], { timeout: 2_000 })
  if (probe.code !== 0) return
  pi.on("tool_call", async (event: ToolCallEvent) => {
    try {
      if (event.toolName !== "bash") return
      const input = (event as any).input as { command?: string }
      if (!input?.command || input.command.startsWith("delegation-core ")) return
      const r = await pi.exec("delegation-core", ["rewrite", input.command], { timeout: 2_000 })
      const rewritten = r.stdout.trim()
      if (r.code === 3 && rewritten && rewritten !== input.command) input.command = rewritten
    } catch {
      // Fail open: never block a command on an unexpected error.
    }
  })
}
