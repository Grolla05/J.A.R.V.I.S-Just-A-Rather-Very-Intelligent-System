import { useRef, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { Paperclip, SendHorizontal } from "lucide-react";
import AttachmentPreview from "./AttachmentPreview";

export default function ChatInput({
  inputValue,
  setInputValue,
  attachedFiles,
  onFileChange,
  onFilesDropped,
  onRemoveFile,
  onSend,
}) {
  const fileInputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };
  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };
  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files?.length) {
      onFilesDropped?.(e.dataTransfer.files);
    }
  };

  return (
    <div className="w-full max-w-2xl mb-8">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,audio/*"
        multiple
        className="hidden"
        onChange={onFileChange}
      />

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`w-full p-3 flex flex-col gap-2 rounded-2xl bg-white/5 border transition-colors ${
          isDragging ? "border-cyan-400/60" : "border-white/10"
        }`}
      >
        {attachedFiles.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            <AnimatePresence>
              {attachedFiles.map((f) => (
                <AttachmentPreview key={f.id} file={f} onRemove={onRemoveFile} />
              ))}
            </AnimatePresence>
          </div>
        )}

        <textarea
          rows={2}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Peça ao JARVIS ou digite um comando..."
          className="w-full bg-transparent border-none outline-none resize-none text-sm text-white/90 placeholder-white/25 leading-relaxed"
        />

        <div className="flex items-center justify-between">
          <button
            onClick={() => fileInputRef.current?.click()}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-white/50 hover:text-white/90 hover:bg-white/10 transition-colors cursor-pointer"
            title="Anexar arquivo"
          >
            <Paperclip size={14} />
          </button>
          <button
            onClick={() => onSend()}
            className="w-8 h-8 flex items-center justify-center rounded-lg bg-cyan-500/30 text-white/90 hover:bg-cyan-500/50 transition-colors cursor-pointer"
            title="Enviar"
          >
            <SendHorizontal size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
