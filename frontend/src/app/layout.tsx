import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tim Frontiers — MCP Inspector",
  description: "Inspect remote MCP servers and optional OpenRouter summaries.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
