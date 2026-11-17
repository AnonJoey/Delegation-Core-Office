// Minimal MCP client over Streamable HTTP: initialize once, then tools/call.
// Uses the host's ctx.http.fetch so the call passes Paperclip's http.outbound gate.

type Fetch = (url: string, init: { method: string; headers?: Record<string, string>; body?: string }) => Promise<{
  status: number;
  headers: { get(name: string): string | null };
  text(): Promise<string>;
}>;

export class McpClient {
  private sessionId: string | null = null;
  private nextId = 1;
  private fetch: Fetch;
  private url: string;
  private token: string;

  constructor(fetch: Fetch, url: string, token: string) {
    this.fetch = fetch;
    this.url = url;
    this.token = token;
  }

  private async rpc(method: string, params: unknown): Promise<any> {
    const headers: Record<string, string> = {
      "content-type": "application/json",
      accept: "application/json, text/event-stream",
      authorization: `Bearer ${this.token}`,
    };
    if (this.sessionId) headers["mcp-session-id"] = this.sessionId;
    const res = await this.fetch(this.url, {
      method: "POST",
      headers,
      body: JSON.stringify({ jsonrpc: "2.0", id: this.nextId++, method, params }),
    });
    const sid = res.headers.get("mcp-session-id");
    if (sid) this.sessionId = sid;
    const raw = await res.text();
    if (res.status >= 400) throw new Error(`delegation-core HTTP ${res.status}: ${raw.slice(0, 300)}`);
    // The server may answer as plain JSON or as one SSE "data:" frame.
    const body = raw.trimStart().startsWith("{")
      ? raw
      : raw.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5)).join("");
    const msg = JSON.parse(body);
    if (msg.error) throw new Error(`delegation-core ${method}: ${msg.error.message}`);
    return msg.result;
  }

  private async ensureSession(): Promise<void> {
    if (this.sessionId) return;
    await this.rpc("initialize", {
      protocolVersion: "2025-06-18",
      capabilities: {},
      clientInfo: { name: "paperclip-plugin", version: "0.1.0" },
    });
    await this.rpc("notifications/initialized", {}).catch(() => undefined);
  }

  async callTool(name: string, args: Record<string, unknown>): Promise<any> {
    await this.ensureSession();
    const result = await this.rpc("tools/call", { name, arguments: args });
    const text = (result?.content ?? []).map((c: any) => c.text ?? "").join("");
    if (result?.isError) throw new Error(text || `${name} failed`);
    const data = text ? JSON.parse(text) : null;
    // delegation-core reports bad input as {"error": ..., "category": ...}, not isError.
    if (data && typeof data === "object" && "error" in data) throw new Error(`${name}: ${data.error}`);
    return data;
  }
}
