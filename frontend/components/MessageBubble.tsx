"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "@/app/chat/page";

interface Props {
  message: ChatMessage;
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] bg-sar-orange/20 border border-sar-orange/30 rounded-2xl rounded-tr-sm px-4 py-3">
          <p className="text-sar-text text-sm whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3 items-start">
      {/* Avatar */}
      <div className="shrink-0 w-8 h-8 rounded-full bg-sar-orange/20 border border-sar-orange/40 flex items-center justify-center text-sm">
        🔍
      </div>

      <div className="flex-1 min-w-0">
        <div className="bg-sar-panel border border-sar-border rounded-2xl rounded-tl-sm px-4 py-3">
          {message.streaming && !message.content ? (
            <span className="text-sar-muted text-sm italic">Thinking…</span>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none text-sar-text text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {/* Agent attribution */}
        {message.agents && message.agents.length > 0 && (
          <p className="mt-1 text-xs text-sar-muted pl-1">
            via {message.agents.join(" · ")}
          </p>
        )}
      </div>
    </div>
  );
}
