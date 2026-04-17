"use client";

import type { AttachedFile } from "@/app/chat/page";

interface Props {
  files: AttachedFile[];
  onRemove: (index: number) => void;
}

function FileIcon({ file }: { file: File }) {
  if (file.type.startsWith("image/")) return <span>🖼️</span>;
  if (file.type === "application/pdf") return <span>📄</span>;
  return <span>📎</span>;
}

export default function FilePreview({ files, onRemove }: Props) {
  if (files.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 px-4 pt-2">
      {files.map((af, i) => (
        <div
          key={i}
          className="flex items-center gap-2 bg-sar-dark border border-sar-border rounded-lg px-3 py-1.5 text-sm"
        >
          {af.preview ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={af.preview} alt={af.file.name} className="w-6 h-6 object-cover rounded" />
          ) : (
            <FileIcon file={af.file} />
          )}
          <span className="text-sar-text max-w-[120px] truncate">{af.file.name}</span>
          <button
            onClick={() => onRemove(i)}
            className="text-sar-muted hover:text-red-400 transition-colors ml-1"
            aria-label="Remove file"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
