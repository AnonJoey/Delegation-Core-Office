import { definePlugin } from "@paperclipai/plugin-sdk";
import type { PluginEvent, ToolResult } from "@paperclipai/plugin-sdk";
import { TOOL_NAMES } from "./manifest.js";
import { McpClient } from "./mcp.js";

// One client per company: config and token are company-scoped.
const clients = new Map<string, McpClient>();

export default definePlugin({
  async setup(ctx) {
    async function client(companyId: string): Promise<{ mcp: McpClient; config: any }> {
      const config = (await ctx.config.get(companyId)) as any;
      if (!config?.daemonUrl || !config?.tokenSecretRef) {
        throw new Error("delegation-core memory: set daemonUrl and tokenSecretRef in the plugin settings");
      }
      let mcp = clients.get(companyId);
      if (!mcp) {
        const token = await ctx.secrets.resolve(config.tokenSecretRef, { companyId, configPath: "tokenSecretRef" });
        mcp = new McpClient((url, init) => ctx.http.fetch(url, init) as any, config.daemonUrl, String(token));
        clients.set(companyId, mcp);
      }
      return { mcp, config };
    }

    ctx.tools.register(
      TOOL_NAMES.recall,
      {
        displayName: "Recall from memory",
        description: "Search the company's memory before acting.",
        parametersSchema: {
          type: "object",
          properties: { query: { type: "string" }, topK: { type: "number" } },
          required: ["query"],
        },
      },
      async (params, runCtx): Promise<ToolResult> => {
        const p = params as { query: string; topK?: number };
        const { mcp } = await client(runCtx.companyId);
        const bundle = await mcp.callTool("memory_query", {
          scope: { companyId: runCtx.companyId, agentId: runCtx.agentId, projectId: runCtx.projectId },
          query: p.query,
          top_k: p.topK ?? 5,
          intent: "answer",
        });
        const snippets = bundle?.snippets ?? [];
        return {
          content: snippets.length
            ? snippets.map((s: any, i: number) => `${i + 1}. ${s.summary ? s.summary + ": " : ""}${s.text}`).join("\n\n")
            : "Nothing in memory for this query.",
          data: bundle,
        };
      },
    );

    ctx.tools.register(
      TOOL_NAMES.remember,
      {
        displayName: "Remember",
        description: "Store a durable fact or decision in the company's memory.",
        parametersSchema: {
          type: "object",
          properties: { text: { type: "string" }, summary: { type: "string" }, agentOnly: { type: "boolean" } },
          required: ["text"],
        },
      },
      async (params, runCtx): Promise<ToolResult> => {
        const p = params as { text: string; summary?: string; agentOnly?: boolean };
        const { mcp } = await client(runCtx.companyId);
        const scope: Record<string, string> = { companyId: runCtx.companyId };
        if (p.agentOnly && runCtx.agentId) scope.agentId = runCtx.agentId;
        const out = await mcp.callTool("memory_upsert", {
          scope,
          records: [{ text: p.text, summary: p.summary ?? "" }],
          source: { kind: "run", companyId: runCtx.companyId, runId: runCtx.runId },
        });
        return { content: "Stored in memory.", data: out };
      },
    );

    // post_run_capture: what a finished run produced becomes residue in memory.
    ctx.events.on("agent.run.finished", async (event: PluginEvent) => {
      const companyId = (event as any).companyId;
      const payload = (event as any).payload ?? {};
      if (!companyId) return;
      const { mcp, config } = await client(companyId);
      if (config.captureRuns === false) return;
      const text = String(payload.summary ?? payload.output ?? "").trim();
      if (!text) return;
      await mcp.callTool("memory_capture", {
        scope: { companyId, agentId: payload.agentId },
        source: { kind: "run", companyId, runId: payload.runId },
        payload: { text, metadata: { hook: "post_run_capture" } },
        mode: "capture_residue",
      });
    });
  },
});
