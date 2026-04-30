"use client";

import { ChatMarkdown } from "@/components/ChatMarkdown";
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
  const [serviceActive, setServiceActive] = useState<boolean | null>(null);
  const [accountVerified, setAccountVerified] = useState(false);
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
      if (typeof data?.verified === "boolean") {
        setAccountVerified(data.verified);
      }
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
    setAccountVerified(false);
    setMessages([]);
  }

  const statusLabel =
    !apiBase ? "Offline" : serviceActive === null ? "Connecting…" : serviceActive ? "Connected" : "Unavailable";

  const showEmpty = messages.length === 0 && !loading;

  return (
    <div className="app-shell">
      <header className="brand-header">
        <div className="brand-header-inner">
          <div className="brand-lockup">
            <span className="brand-mark" aria-hidden />
            <div>
              <p className="brand-name">Meridian Electronics</p>
              <p className="brand-tagline">Support</p>
            </div>
          </div>
          <div className="brand-meta">
            <span
              className={`status-dot ${serviceActive ? "status-dot--ok" : serviceActive === false || !apiBase ? "status-dot--bad" : ""}`}
              aria-hidden
            />
            <span className="status-text">{statusLabel}</span>
            {accountVerified && apiBase && (
              <span className="badge-verified" aria-live="polite">
                Verified
              </span>
            )}
          </div>
        </div>
      </header>

      {!apiBase && (
        <p className="config-banner">Set <code>NEXT_PUBLIC_API_URL</code> to your API URL, then rebuild.</p>
      )}

      <main className="chat-main">
        <div className="chat-scroll">
          {showEmpty && (
            <div className="empty-chat">
              <h2 className="empty-title">How can we help?</h2>
              <p className="empty-body">
                Send a message to chat with support. Ask about products, pricing, or your orders and account—we’re
                here to assist.
              </p>
            </div>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`msg-row ${msg.role === "user" ? "msg-row--user" : "msg-row--assistant"}`}
            >
              {msg.role === "assistant" && <span className="msg-avatar" aria-hidden />}
              <div className={`bubble ${msg.role === "user" ? "bubble-user" : "bubble-assistant"}`}>
                {msg.role === "assistant" && (
                  <div className="bubble-head">
                    <span className="bubble-name">Meridian</span>
                  </div>
                )}
                {msg.role === "assistant" ? (
                  <ChatMarkdown content={msg.content} />
                ) : (
                  <span className="bubble-text-plain">{msg.content}</span>
                )}
              </div>
            </div>
          ))}
          {loading && (
            <div className="msg-row msg-row--assistant">
              <span className="msg-avatar" aria-hidden />
              <div className="bubble bubble-assistant bubble--typing">
                <div className="bubble-head">
                  <span className="bubble-name">Meridian</span>
                </div>
                <span className="typing" aria-label="Assistant is typing">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </main>

      {error && <div className="alert">{error}</div>}

      <footer className="composer-dock">
        <div className="composer-card">
          <textarea
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder={apiBase ? "Message Meridian Electronics…" : "API URL not configured"}
            disabled={!apiBase || loading}
            className="composer-input"
          />
          <button type="button" className="btn-send" disabled={!apiBase || loading || !input.trim()} onClick={() => void send()}>
            Send
          </button>
        </div>
        <button type="button" className="btn-secondary" onClick={() => void resetChat()}>
          New conversation
        </button>
      </footer>
    </div>
  );
}
