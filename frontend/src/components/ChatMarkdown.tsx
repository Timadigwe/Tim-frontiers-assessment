"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Props = {
  content: string;
  className?: string;
};

/**
 * Renders LLM markdown (GFM: lists, tables, strikethrough, links).
 * HTML is not interpreted as raw HTML (react-markdown default — safe).
 */
export function ChatMarkdown({ content, className }: Props) {
  return (
    <div className={className ?? "chat-md"}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
