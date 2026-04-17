"use client";

import { useCallback, useRef, useState } from "react";
import type { AttachedFile } from "@/app/chat/page";
import FilePreview from "./FilePreview";

interface Props {
  onSend: (text: string, files: AttachedFile[]) => void;
  onStop: () => void;
  isStreaming: boolean;
}

export default function InputBar({ onSend, onStop, isStreaming }: Props) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<AttachedFile[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const addFiles = useCallback((incoming: FileList | File[]) => {
    const arr = Array.from(incoming);
    const newItems: AttachedFile[] = arr.map((file) => {
      const preview = file.type.startsWith("image/")
        ? URL.createObjectURL(file)
        : undefined;
      return { file, preview };
    });
    setFiles((prev) => [...prev, ...newItems]);
  }, []);

  const handleRemoveFile = (index: number) => {
    setFiles((prev) => {
      const copy = [...prev];
      if (copy[index].preview) URL.revokeObjectURL(copy[index].preview!);
      copy.splice(index, 1);
      return copy;
    });
  };

  const handleSend = () => {
    if (!text.trim() && files.length === 0) return;
    onSend(text, files);
    setText("");
    setFiles([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files);
    }
  };

  return (
    <div
      className={`transition-colors ${isDragging ? "bg-sar-orange/10" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
    >
      <FilePreview files={files} onRemove={handleRemoveFile} />

      <div className="flex items-end gap-3 px-4 py-3">
        {/* File attach button */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isStreaming}
          className="shrink-0 text-sar-muted hover:text-sar-text disabled:opacity-40 transition-colors pb-2"
          title="Attach files (images, PDFs, text)"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
              d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
          </svg>
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/*,.pdf,.txt,.csv,.json,.md"
          className="hidden"
          onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }}
        />

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isStreaming}
          placeholder={isDragging ? "Drop files here…" : "Describe the SAR situation or ask a question…"}
          rows={1}
          className="flex-1 resize-none bg-sar-dark border border-sar-border rounded-xl px-4 py-2.5 text-sm text-sar-text placeholder-sar-muted focus:outline-none focus:border-sar-orange/60 disabled:opacity-50 max-h-40 overflow-y-auto"
          style={{ lineHeight: "1.5" }}
          onInput={(e) => {
            const el = e.currentTarget;
            el.style.height = "auto";
            el.style.height = Math.min(el.scrollHeight, 160) + "px";
          }}
        />

        {/* Send / Stop button */}
        {isStreaming ? (
          <button
            onClick={onStop}
            className="shrink-0 w-9 h-9 rounded-full bg-red-500/20 border border-red-500/40 text-red-400 hover:bg-red-500/30 transition-colors flex items-center justify-center"
            title="Stop"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="6" width="12" height="12" rx="1" />
            </svg>
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!text.trim() && files.length === 0}
            className="shrink-0 w-9 h-9 rounded-full bg-sar-orange disabled:bg-sar-orange/30 text-white disabled:text-white/40 hover:bg-sar-orange/80 transition-colors flex items-center justify-center"
            title="Send (Enter)"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 19V5m0 0l-7 7m7-7l7 7" />
            </svg>
          </button>
        )}
      </div>

      <p className="text-center text-xs text-sar-muted pb-2 hidden sm:block">
        Attach images or PDFs · Shift+Enter for new line · Enter to send
      </p>
    </div>
  );
}
