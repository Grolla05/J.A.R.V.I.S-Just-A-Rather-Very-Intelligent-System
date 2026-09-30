import { memo, useRef, useEffect, useState, useMemo, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import AttachmentPreview from "./AttachmentPreview";
import { MD_COMPONENTS } from "./MarkdownComponents";
import "katex/dist/katex.min.css";

const STREAMING_ID = "streaming-msg";

// Referências estáveis: evitam que o ReactMarkdown veja props "novas" a cada render
const REMARK_PLUGINS = [remarkGfm, remarkMath];
const REHYPE_PLUGINS = [rehypeKatex];

const preprocessMarkdown = (text) => {
  if (!text) return "";
  // Substitui \[ ... \] por $$ ... $$ para blocos de matemática
  let processed = text.replace(/\\\[([\s\S]*?)\\\]/g, (_, equation) => {
    return `\n$$\n${equation.trim()}\n$$\n`;
  });
  // Substitui \( ... \) por $ ... $ para matemática em linha
  processed = processed.replace(/\\\(([\s\S]*?)\\\)/g, (_, equation) => {
    return `$${equation.trim()}$`;
  });
  return processed;
};

// Só re-parseia markdown/KaTeX quando o texto DESTA mensagem muda
const MarkdownBody = memo(function MarkdownBody({ text }) {
  const processed = useMemo(() => preprocessMarkdown(text), [text]);
  return (
    <div className="jarvis-md text-white/90 text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={REHYPE_PLUGINS}
        components={MD_COMPONENTS}
      >
        {processed}
      </ReactMarkdown>
    </div>
  );
});

const actionBtn =
  "text-[11px] text-white/40 hover:text-white/80 transition-colors cursor-pointer outline-none";

const MessageItem = memo(function MessageItem({
  msg,
  isEditing,
  editingText,
  isCopied,
  isLastUser,
  onCopy,
  onStartEdit,
  onCancelEdit,
  onEditTextChange,
  onSubmitEdit,
  onRegenerateMessage,
}) {
  const isJarvis = msg.sender === "jarvis";

  return (
    <div className={`flex w-full group ${isJarvis ? "justify-start" : "justify-end"}`}>
      <div className={`flex flex-col gap-1 max-w-[80%] ${isJarvis ? "items-start" : "items-end"}`}>
        {isEditing ? (
          <div className="flex flex-col gap-2 min-w-[280px] w-full">
            <textarea
              value={editingText}
              onChange={(e) => onEditTextChange(e.target.value)}
              className="w-full bg-white/5 border border-white/15 rounded-lg p-3 text-white/90 text-sm outline-none focus:border-white/40 resize-y min-h-[70px] max-h-[200px] glass-scrollbar"
              autoFocus
              placeholder="Edite sua mensagem..."
            />
            <div className="flex justify-end gap-3">
              <button onClick={onCancelEdit} className={actionBtn}>
                Cancelar
              </button>
              <button
                onClick={() => onSubmitEdit(msg, editingText)}
                className="text-[11px] text-cyan-400 hover:text-cyan-300 transition-colors cursor-pointer outline-none"
              >
                Salvar e enviar
              </button>
            </div>
          </div>
        ) : (
          <div
            className={
              isJarvis
                ? "text-sm"
                : "px-4 py-2.5 rounded-2xl bg-white/10 text-sm text-white/90"
            }
          >
            {isJarvis ? (
              <MarkdownBody text={msg.text} />
            ) : (
              <span className="whitespace-pre-wrap">{msg.text}</span>
            )}

            {msg.attachments?.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {msg.attachments.map((f) => (
                  <AttachmentPreview key={f.id} file={f} />
                ))}
              </div>
            )}
          </div>
        )}

        {msg.id !== STREAMING_ID && !isEditing && (
          <div className="flex items-center gap-3 px-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button onClick={() => onCopy(msg.id, msg.text)} className={actionBtn}>
              {isCopied ? "Copiado" : "Copiar"}
            </button>
            {!isJarvis && isLastUser && (
              <button onClick={() => onStartEdit(msg)} className={actionBtn}>
                Editar
              </button>
            )}
            {isJarvis && onRegenerateMessage && (
              <button
                onClick={() => onRegenerateMessage(msg.id)}
                className={actionBtn}
              >
                Regenerar
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
});

export default function MessageList({
  messages = [],
  isThinking,
  onEditMessage,
  onRegenerateMessage,
}) {
  const messagesEndRef = useRef(null);
  const copyTimerRef = useRef(null);
  const [copiedId, setCopiedId] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editingText, setEditingText] = useState("");

  useEffect(() => () => clearTimeout(copyTimerRef.current), []);

  const handleCopy = useCallback((msgId, text) => {
    navigator.clipboard.writeText(text);
    setCopiedId(msgId);
    clearTimeout(copyTimerRef.current);
    copyTimerRef.current = setTimeout(() => setCopiedId(null), 2000);
  }, []);

  const handleStartEdit = useCallback((msg) => {
    setEditingId(msg.id);
    setEditingText(msg.text);
  }, []);

  const handleCancelEdit = useCallback(() => setEditingId(null), []);

  const handleSubmitEdit = useCallback(
    (msg, text) => {
      if (text.trim() && text.trim() !== msg.text) {
        onEditMessage(msg.id, text);
      }
      setEditingId(null);
    },
    [onEditMessage],
  );

  // Durante o streaming, scroll "auto": um smooth novo por chunk vira thrash de layout
  const isStreaming = messages[messages.length - 1]?.id === STREAMING_ID;
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: isStreaming ? "auto" : "smooth",
    });
  }, [messages, isThinking, isStreaming]);

  const lastUserMessageId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].sender === "user") return messages[i].id;
    }
    return undefined;
  }, [messages]);

  return (
    <div className="flex-1 min-h-0 w-full flex flex-col items-center overflow-hidden">
      {messages.length > 0 ? (
        <div className="w-full max-w-3xl flex-1 min-h-0 overflow-y-auto my-4 pr-2 flex flex-col gap-5 glass-scrollbar select-text">
          {messages.map((msg) => (
            <MessageItem
              key={msg.id}
              msg={msg}
              isEditing={editingId === msg.id}
              editingText={editingId === msg.id ? editingText : ""}
              isCopied={copiedId === msg.id}
              isLastUser={msg.id === lastUserMessageId}
              onCopy={handleCopy}
              onStartEdit={handleStartEdit}
              onCancelEdit={handleCancelEdit}
              onEditTextChange={setEditingText}
              onSubmitEdit={handleSubmitEdit}
              onRegenerateMessage={onRegenerateMessage}
            />
          ))}

          {isThinking && (
            <p className="text-sm text-white/40 animate-pulse">Pensando…</p>
          )}
          <div ref={messagesEndRef} />
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-end select-none text-center max-w-2xl pb-16">
          <h2 className="text-2xl font-semibold tracking-tight text-white/90">
            Como posso ajudar, Felipe?
          </h2>
        </div>
      )}
    </div>
  );
}
