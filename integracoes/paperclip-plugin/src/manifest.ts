import type { PaperclipPluginManifestV1 } from "@paperclipai/plugin-sdk";

export const PLUGIN_ID = "delegation-core.memory";

export const TOOL_NAMES = {
  recall: "recall",
  remember: "remember",
} as const;

const manifest: PaperclipPluginManifestV1 = {
  id: PLUGIN_ID,
  apiVersion: 1,
  version: "0.1.0",
  displayName: "delegation-core memory",
  description:
    "Gives every agent of a company a shared, searchable memory kept by a delegation-core daemon: " +
    "recall before acting, remember what was decided, and capture each finished run.",
  author: "delegation-core",
  categories: ["automation"],
  capabilities: [
    "agent.tools.register",
    "events.subscribe",
    "http.outbound",
    "secrets.read-ref",
    "instance.settings.register",
  ],
  entrypoints: {
    worker: "./dist/worker.js",
  },
  instanceConfigSchema: {
    type: "object",
    properties: {
      daemonUrl: {
        type: "string",
        title: "delegation-core MCP URL",
        description: "The daemon's MCP endpoint, e.g. http://127.0.0.1:8787/mcp. Must be reachable from the Paperclip server.",
      },
      tokenSecretRef: {
        type: "string",
        title: "Token secret",
        description: "Secret holding a delegation-core client token (create one with `delegation-core token create paperclip --write`).",
      },
      captureRuns: {
        type: "boolean",
        title: "Capture finished runs",
        default: true,
      },
    },
    required: ["daemonUrl", "tokenSecretRef"],
  },
  tools: [
    {
      name: TOOL_NAMES.recall,
      displayName: "Recall from memory",
      description: "Search the company's memory before acting. Returns the most relevant snippets.",
      parametersSchema: {
        type: "object",
        properties: {
          query: { type: "string" },
          topK: { type: "number" },
        },
        required: ["query"],
      },
    },
    {
      name: TOOL_NAMES.remember,
      displayName: "Remember",
      description: "Store a durable fact or decision in the company's memory.",
      parametersSchema: {
        type: "object",
        properties: {
          text: { type: "string" },
          summary: { type: "string" },
          agentOnly: { type: "boolean", description: "Visible only to this agent" },
        },
        required: ["text"],
      },
    },
  ],
};

export default manifest;
