import { useState, useEffect } from "react";
import { Pencil, Pin } from "lucide-react";

export default function ChatSidebar({
  onNewChat,
  onSelectSession,
  onRenameSession,
  onTogglePin,
  recentSessions = [],
  currentSessionId,
}) {
  const [editingSessionId, setEditingSessionId] = useState(null);
  const [editTitleText, setEditTitleText] = useState("");
  const [contextMenu, setContextMenu] = useState(null); // { x, y, sessionId, isPinned, title }

  // Fecha o menu de contexto ao clicar em qualquer outro lugar
  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [contextMenu]);

  const startEdit = (session) => {
    setEditingSessionId(session.id);
    setEditTitleText(session.title);
  };

  const handleSaveTitle = (sessionId) => {
    if (editTitleText.trim() !== "") {
      onRenameSession(sessionId, editTitleText.trim());
    }
    setEditingSessionId(null);
  };

  const pinnedSessions = recentSessions.filter((s) => s.is_pinned);
  const unpinnedSessions = recentSessions.filter((s) => !s.is_pinned);

  const renderSessionItem = (session) => {
    const isActive = session.id === currentSessionId;
    const isEditing = editingSessionId === session.id;

    return (
      <div
        key={session.id}
        className={`group flex items-center justify-between text-xs py-2 px-3 rounded-lg cursor-pointer transition-colors ${
          isActive
            ? "bg-white/10 text-white"
            : "text-white/50 hover:text-white/90 hover:bg-white/5"
        }`}
        onContextMenu={(e) => {
          e.preventDefault();
          setContextMenu({
            x: e.clientX,
            y: e.clientY,
            sessionId: session.id,
            isPinned: session.is_pinned,
            title: session.title,
          });
        }}
      >
        {isEditing ? (
          <input
            type="text"
            value={editTitleText}
            onChange={(e) => setEditTitleText(e.target.value)}
            onBlur={() => handleSaveTitle(session.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSaveTitle(session.id);
              else if (e.key === "Escape") setEditingSessionId(null);
            }}
            className="w-full bg-black/40 border border-white/20 rounded px-1.5 py-0.5 text-white outline-none text-xs"
            autoFocus
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <div
            className="flex items-center justify-between w-full min-w-0"
            onClick={() => onSelectSession(session.id)}
            onDoubleClick={(e) => {
              e.stopPropagation();
              startEdit(session);
            }}
          >
            <span className="truncate flex-1 pr-2">{session.title}</span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                startEdit(session);
              }}
              className="opacity-0 group-hover:opacity-100 transition-opacity text-white/40 hover:text-white p-0.5 shrink-0"
              title="Renomear conversa"
            >
              <Pencil size={11} />
            </button>
          </div>
        )}
      </div>
    );
  };

  return (
    <aside className="w-60 h-full flex flex-col p-3 gap-3 z-40 relative select-none bg-black/40 border-r border-white/5">
      <button
        onClick={onNewChat}
        className="w-full py-2 px-3 flex items-center justify-between text-xs text-white/75 rounded-lg border border-white/10 hover:bg-white/5 transition-colors cursor-pointer"
      >
        <span>+ Nova conversa</span>
        <span className="text-[9px] text-white/40">Ctrl K</span>
      </button>

      <div className="flex-1 min-h-0 flex flex-col gap-3">
        {pinnedSessions.length > 0 && (
          <div className="flex flex-col gap-1 max-h-[40%] overflow-y-auto glass-scrollbar border-b border-white/5 pb-2">
            <span className="text-[9px] font-semibold text-white/30 uppercase tracking-wider px-3 mb-1 flex items-center gap-1.5">
              <Pin size={9} /> Fixados
            </span>
            {pinnedSessions.map(renderSessionItem)}
          </div>
        )}

        <div className="flex-1 overflow-y-auto flex flex-col gap-1 glass-scrollbar">
          <span className="text-[9px] font-semibold text-white/30 uppercase tracking-wider px-3 mb-1">
            Recentes
          </span>
          {unpinnedSessions.length === 0 ? (
            <span className="text-[11px] text-white/25 px-3 py-2 italic">
              Nenhuma conversa recente
            </span>
          ) : (
            unpinnedSessions.map(renderSessionItem)
          )}
        </div>
      </div>

      {contextMenu && (
        <div
          style={{ position: "fixed", top: contextMenu.y, left: contextMenu.x }}
          className="z-[9999] min-w-[160px] p-1 flex flex-col rounded-lg bg-neutral-900 border border-white/10"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={() => {
              setEditingSessionId(contextMenu.sessionId);
              setEditTitleText(contextMenu.title);
              setContextMenu(null);
            }}
            className="w-full text-left text-xs px-3 py-2 rounded-md flex items-center gap-2 text-white/80 hover:bg-white/10 whitespace-nowrap cursor-pointer"
          >
            <Pencil size={11} /> Editar título
          </button>
          <button
            onClick={() => {
              onTogglePin(contextMenu.sessionId, !contextMenu.isPinned);
              setContextMenu(null);
            }}
            className="w-full text-left text-xs px-3 py-2 rounded-md flex items-center gap-2 text-white/80 hover:bg-white/10 whitespace-nowrap cursor-pointer"
          >
            <Pin size={11} /> {contextMenu.isPinned ? "Desafixar chat" : "Fixar chat"}
          </button>
        </div>
      )}
    </aside>
  );
}
