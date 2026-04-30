"use client";

import { newSessionId } from "@/lib/sessionId";
import { useEffect, useRef, useState } from "react";

const apiBase = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";

type Msg = { role: "user" | "assistant"; content: string };

function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return "";
  const k = "support_chat_session_id";
  let id = sessionStorage.getItem(k);
  if (!id) {
    id = newSessionId();
    sessionStorage.setItem(k, id);
  }
  return id;
}

export default function Page() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** null = still checking; true/false = health result */
  const [serviceActive, setServiceActive] = useState<boolean | null>(null);
  const [sessionId, setSessionId] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setSessionId(getOrCreateSessionId());
  }, []);

  useEffect(() => {
    if (!apiBase) {
      setServiceActive(null);
      return;
    }
    setServiceActive(null);
    fetch(`${apiBase}/api/health`)
      .then((r) => setServiceActive(r.ok))
      .catch(() => setServiceActive(false));
  }, [apiBase]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send() {
    const text = input.trim();
    if (!text || !apiBase || !sessionId) return;
    setInput("");
    setError(null);
    setMessages((m) => [...m, { role: "user", content: text }]);
    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: text }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = typeof data?.detail === "string" ? data.detail : JSON.stringify(data);
        throw new Error(detail || res.statusText);
      }
      const reply = typeof data?.reply === "string" ? data.reply : "";
      setMessages((m) => [...m, { role: "assistant", content: reply || "(No reply)" }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setMessages((m) => m.slice(0, -1));
    } finally {
      setLoading(false);
    }
  }

  async function resetChat() {
    if (!apiBase || !sessionId) return;
    setError(null);
    try {
      await fetch(`${apiBase}/api/session/reset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch {
      /* ignore */
    }
    const id = newSessionId();
    sessionStorage.setItem("support_chat_session_id", id);
    setSessionId(id);
    setMessages([]);
  }

  const statusLabel =
    !apiBase ? "Not connected" : serviceActive === null ? "Connecting…" : serviceActive ? "Active" : "Unavailable";

  return (
    <div className="layout">
      <header className="header">
        <p className="header-kicker">Customer support</p>
        <h1 className="header-title">Support</h1>
        <p className="header-sub">Help with products, orders, and account.</p>
        <div className="meta">
          <span
            className={`pill ${
              serviceActive ? "pill-ok" : serviceActive === false || !apiBase ? "pill-off" : ""
            }`}
            aria-live="polite"
          >
            {statusLabel}
          </span>
        </div>
      </header>

      {!apiBase && (
        <p className="empty-hint">Build with NEXT_PUBLIC_API_URL pointing at the API (CI sets this from App Runner).</p>
      )}

      <div className="chat-scroll">
        {messages.length === 0 && apiBase && (
          <p className="empty-hint">
            Ask about stock, search products, verify with email + PIN for orders, or start an order.
          </p>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`bubble ${msg.role === "user" ? "bubble-user" : "bubble-assistant"}`}>
            {msg.role === "assistant" && <div className="bubble-label">Assistant</div>}
            {msg.content}
          </div>
        ))}
        {loading && (
          <div className="bubble bubble-assistant">
            <div className="bubble-label">Assistant</div>
            …
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="composer-wrap">
        <div className="composer">
          <textarea
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder={apiBase ? "Message…" : "API URL not configured"}
            disabled={!apiBase || loading}
          />
          <button type="button" className="btn-send" disabled={!apiBase || loading || !input.trim()} onClick={() => void send()}>
            Send
          </button>
        </div>
        <button type="button" className="btn-text" onClick={() => void resetChat()}>
          Clear conversation
        </button>
      </div>
    </div>
  );
}
