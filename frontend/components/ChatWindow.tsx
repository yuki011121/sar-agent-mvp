"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/app/chat/page";
import MessageBubble from "./MessageBubble";
import ClueMeisterBubble from "./ClueMeisterBubble";
import PathMapBubble from "./PathMapBubble";

interface Props {
  messages: ChatMessage[];
  isStreaming: boolean;
}

export default function ChatWindow({ messages, isStreaming }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="h-full overflow-y-auto px-4 py-6">
      <div className="max-w-3xl mx-auto space-y-4">
        {messages.map((msg) =>
          msg.isClueMeister ? (
            <div key={msg.id} className="flex gap-3 items-start">
              <div className="shrink-0 w-8 h-8 rounded-full bg-sar-orange/20 border border-sar-orange/40 flex items-center justify-center text-sm">
                🔬
              </div>
              <div className="flex-1 min-w-0">
                {msg.streaming ? (
                  <div className="rounded-lg border border-sar-border bg-sar-panel px-4 py-3">
                    <span className="text-sar-muted text-sm italic">
                      {msg.content || "Analyzing…"}
                    </span>
                  </div>
                ) : msg.clueMeisterData ? (
                  <ClueMeisterBubble data={msg.clueMeisterData} />
                ) : (
                  <div className="rounded-lg border border-sar-border bg-sar-panel px-4 py-3">
                    <span className="text-sm text-sar-text">{msg.content}</span>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div key={msg.id}>
              <MessageBubble message={msg} />
              {msg.pathData && <PathMapBubble data={msg.pathData} />}
            </div>
          )
        )}

        {isStreaming && messages[messages.length - 1]?.streaming && (
          <div className="flex gap-1 pl-12 mt-1">
            <span className="w-2 h-2 bg-sar-orange rounded-full animate-bounce [animation-delay:0ms]" />
            <span className="w-2 h-2 bg-sar-orange rounded-full animate-bounce [animation-delay:150ms]" />
            <span className="w-2 h-2 bg-sar-orange rounded-full animate-bounce [animation-delay:300ms]" />
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
