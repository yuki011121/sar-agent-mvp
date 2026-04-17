"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/app/chat/page";
import MessageBubble from "./MessageBubble";

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
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

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
