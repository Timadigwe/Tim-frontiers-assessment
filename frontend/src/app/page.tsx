"use client";

import { useEffect, useState } from "react";

const apiBase = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";

type Transport = "auto" | "sse" | "streamable_http";

export default function Page() {
  const [mcpUrl, setMcpUrl] = useState("");
  const [headerJson, setHeaderJson] = useState("");
  const [transport, setTransport] = useState<Transport>("auto");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [cfg, setCfg] = useState<{ openrouter_configured?: boolean; openrouter_model?: string } | null>(null);

  useEffect(() => {
    if (!apiBase) return;
    fetch(`${apiBase}/api/config`)
      .then((r) => r.json())
      .then(setCfg)
      .catch(() => setCfg({}));
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!apiBase) {
      setError("Build the app with NEXT_PUBLIC_API_URL set to your App Runner API URL (CI does this automatically).");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    let extraHeaders: Record<string, string> = {};
    const raw = headerJson.trim();
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as unknown;
        if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error("Headers must be a JSON object.");
        }
        extraHeaders = Object.fromEntries(
          Object.entries(parsed as Record<string, unknown>).map(([k, v]) => [
            k,
            typeof v === "string" ? v : JSON.stringify(v),
          ]),
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "Invalid headers JSON.");
        setLoading(false);
        return;
      }
    }
    try {
      const res = await fetch(`${apiBase}/api/mcp/inspect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mcp_url: mcpUrl.trim(),
          transport,
          headers: extraHeaders,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = typeof data?.detail === "string" ? data.detail : JSON.stringify(data);
        throw new Error(detail || res.statusText);
      }
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  const orOn = Boolean(cfg?.openrouter_configured);

  return (
    <div className="shell">
      <header className="hero">
        <p className="hero-eyebrow">MCP</p>
        <h1 className="hero-title">Server inspector</h1>
        <p className="hero-desc">
          Connect to a streamable HTTP or SSE endpoint, list tools and resources, and optionally get
          a short OpenRouter summary.
        </p>
      </header>

      <div className="card">
        <div className="meta-row">
          <span
            className={`badge ${orOn ? "badge-on" : ""}`}
            title={orOn ? "OpenRouter is configured on the API" : "Add OPENROUTER_API_KEY to the backend"}
          >
            <span className="badge-dot" aria-hidden />
            OpenRouter {orOn ? "on" : "off"}
            {orOn && cfg?.openrouter_model ? ` · ${cfg.openrouter_model}` : ""}
          </span>
          <span className="badge badge-code" title="API base URL">
            {apiBase || "No API URL (set at build time)"}
          </span>
        </div>

        <form onSubmit={onSubmit}>
          <div className="field">
            <label className="field-label" htmlFor="mcp-url">
              MCP URL
            </label>
            <input
              id="mcp-url"
              className="input"
              type="url"
              required
              value={mcpUrl}
              onChange={(e) => setMcpUrl(e.target.value)}
              placeholder="https://example.com/mcp"
              autoComplete="url"
            />
            <p className="field-hint">Streamable HTTP is usually the host with path <code>/mcp</code>.</p>
          </div>

          <div className="field">
            <label className="field-label" htmlFor="mcp-headers">
              HTTP headers (JSON, optional)
            </label>
            <textarea
              id="mcp-headers"
              className="textarea"
              value={headerJson}
              onChange={(e) => setHeaderJson(e.target.value)}
              placeholder='{"x-player-token": "YourName"}'
              rows={3}
              spellCheck={false}
            />
            <p className="field-hint">Required by some servers (e.g. player token).</p>
          </div>

          <div className="field">
            <label className="field-label" htmlFor="mcp-transport">
              Transport
            </label>
            <select
              id="mcp-transport"
              className="select"
              value={transport}
              onChange={(e) => setTransport(e.target.value as Transport)}
            >
              <option value="auto">Auto (streamable HTTP, then SSE)</option>
              <option value="streamable_http">Streamable HTTP</option>
              <option value="sse">SSE</option>
            </select>
          </div>

          <button type="submit" className="btn" disabled={loading}>
            {loading ? (
              <>
                <span className="btn-spinner" aria-hidden />
                Connecting…
              </>
            ) : (
              "Run inspection"
            )}
          </button>
        </form>
      </div>

      {error && <div className="alert-error">{error}</div>}

      {result && (
        <div className="results">
          {typeof result.openrouter_summary === "string" && result.openrouter_summary && (
            <section>
              <h2 className="section-title">Summary</h2>
              <div className="summary-card">{result.openrouter_summary}</div>
            </section>
          )}
          <section>
            <h2 className="section-title">JSON</h2>
            <pre className="pre-json">{JSON.stringify(result, null, 2)}</pre>
          </section>
        </div>
      )}
    </div>
  );
}
