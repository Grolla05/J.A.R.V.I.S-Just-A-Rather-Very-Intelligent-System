import { useState, useEffect, useCallback, useRef } from "react";
import { getFileStyle } from "./CHAT/fileStyle";
import ChatSidebar from "./CHAT/ChatSidebar";
import MessageList from "./CHAT/MessageList";
import ChatInput from "./CHAT/ChatInput";
import useBridgeAPI from "../hooks/BridgeAPI";

export default function ChatPanel({
  messages = [],
  setMessages,
  currentSessionId,
  setCurrentSessionId,
}) {
  const [inputValue, setInputValue] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState([]);
  
  // Controle de estado das sessões
  const [recentSessions, setRecentSessions] = useState([]);
  
  const { isReady, callApi } = useBridgeAPI();

  // Função geradora de tokens de sessão criptográficos Base64 (URL-safe) de 32 bytes
  const generateSessionToken = useCallback(() => {
    try {
      const array = new Uint8Array(32);
      window.crypto.getRandomValues(array);
      // Converte binário para string Base64 e limpa para formato URL-safe
      return btoa(String.fromCharCode.apply(null, array))
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=+$/, '');
    } catch {
      // Fallback seguro em caso de ausência temporária do crypto no ambiente de desenvolvimento
      return "fallback_session_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9);
    }
  }, []);

  // Busca a lista de sessões recentes do banco de dados SQLite
  const fetchRecentSessions = useCallback(async () => {
    try {
      const sessions = await callApi("get_recent_sessions", 8);
      if (sessions) {
        setRecentSessions(sessions);
        return sessions;
      }
    } catch (err) {
      console.error("Erro ao buscar sessões recentes:", err);
    }
    return [];
  }, [callApi]);

  // Busca e restaura o histórico de mensagens de uma sessão específica
  const fetchChatHistory = useCallback(async (sessionId) => {
    if (!sessionId) return;
    try {
      const history = await callApi("get_chat_history", sessionId, 50);
      if (history) {
        setMessages(history);
      }
    } catch (err) {
      console.error(`Erro ao buscar histórico da sessão '${sessionId}':`, err);
    }
  }, [callApi, setMessages]);

  const hasInitializedRef = useRef(false);

  // Inicializa os dados e sempre começa em uma "Nova Conversa" (Welcome Screen) no primeiro carregamento
  useEffect(() => {
    const initializeSessions = async () => {
      if (isReady && !hasInitializedRef.current) {
        hasInitializedRef.current = true;
        const sessions = await fetchRecentSessions();
        if (currentSessionId) {
          // Se já temos uma sessão carregada, garante que o histórico é sincronizado se ela existir no banco
          const exists = sessions && sessions.some((s) => s.id === currentSessionId);
          if (exists) {
            fetchChatHistory(currentSessionId);
          }
        } else {
          // Abre sempre na tela de "Nova Conversa" por padrão, sem auto-restaurar a última ativa do banco
          const newId = generateSessionToken();
          setCurrentSessionId(newId);
          setMessages([]);
        }
      }
    };
    initializeSessions();
  }, [isReady, currentSessionId, fetchRecentSessions, fetchChatHistory, generateSessionToken, setCurrentSessionId, setMessages]);

  // Ação de selecionar uma sessão existente na barra lateral (Restauração)
  const handleSelectSession = useCallback((sessionId) => {
    setCurrentSessionId(sessionId);
    fetchChatHistory(sessionId);
  }, [fetchChatHistory, setCurrentSessionId]);

  // Ação de criar um novo chat/sessão (Lazy Creation)
  const handleNewChat = useCallback(() => {
    const newToken = generateSessionToken();
    setCurrentSessionId(newToken);
    setMessages([]);
  }, [generateSessionToken, setCurrentSessionId, setMessages]);

  // Callback de renomear sessão
  const handleRenameSession = useCallback(async (sessionId, newTitle) => {
    try {
      await callApi("update_session_title", sessionId, newTitle);
      fetchRecentSessions();
    } catch (err) {
      console.error("Erro ao renomear sessão:", err);
    }
  }, [callApi, fetchRecentSessions]);

  // Callback de fixar/desafixar sessão
  const handleTogglePin = useCallback(async (sessionId, isPinned) => {
    try {
      await callApi("toggle_session_pin", sessionId, isPinned);
      fetchRecentSessions();
    } catch (err) {
      console.error("Erro ao alternar fixação de sessão:", err);
    }
  }, [callApi, fetchRecentSessions]);

  // Atalho global Ctrl+K (ou Cmd+K no macOS) para criar uma nova conversa
  useEffect(() => {
    const handleGlobalKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        handleNewChat();
      }
    };
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [handleNewChat]);

  // Ref com as mensagens atuais: handlers abaixo leem daqui e mantêm identidade
  // estável (senão mudariam a cada flush do stream e anulariam o React.memo da lista)
  const messagesRef = useRef(messages);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // Callback de edição de mensagem do usuário
  const handleEditMessage = useCallback(async (msgId, newText) => {
    if (!currentSessionId) return;
    try {
      setIsThinking(true);

      // 1. Atualizar a mensagem editada no SQLite
      await callApi("update_history_message", msgId, newText);

      // 2. Apagar todas as mensagens posteriores no SQLite
      const messages = messagesRef.current;
      const index = messages.findIndex((m) => m.id === msgId);
      if (index !== -1) {
        const nextMsg = messages[index + 1];
        if (nextMsg) {
          await callApi("delete_history_from", currentSessionId, nextMsg.id);
        }

        // 3. Truncar a lista local no frontend e atualizar o texto do prompt
        const truncated = messages.slice(0, index + 1);
        truncated[index] = {
          ...truncated[index],
          text: newText,
        };
        setMessages(truncated);
      }

      // 4. Enviar o novo prompt para o Jarvis gerar a resposta alternativa
      if (window.pywebview && window.pywebview.api) {
        callApi("chat_message", newText, currentSessionId);
      } else {
        // Mock fallback
        setTimeout(() => {
          window.receiveChatStream("Esta é uma resposta alternativa para o seu prompt editado.", true, false);
          window.receiveChatStream("", false, true);
        }, 1000);
      }
    } catch (err) {
      console.error("Erro ao editar mensagem:", err);
      setIsThinking(false);
    }
  }, [currentSessionId, callApi, setMessages]);

  // Callback de regeneração de resposta do Jarvis
  const handleRegenerateMessage = useCallback(async (jarvisMsgId) => {
    if (!currentSessionId) return;
    try {
      const messages = messagesRef.current;
      const index = messages.findIndex((m) => m.id === jarvisMsgId);
      if (index === -1) return;

      const userMsg = messages[index - 1];
      if (!userMsg || userMsg.sender !== "user") return;

      setIsThinking(true);

      // 1. Apagar todas as mensagens no SQLite a partir desta mensagem do Jarvis
      await callApi("delete_history_from", currentSessionId, jarvisMsgId);

      // 2. Remover do estado local todas as mensagens a partir do JarvisMsgId
      const truncated = messages.slice(0, index);
      setMessages(truncated);

      // 3. Enviar novamente o prompt do usuário
      if (window.pywebview && window.pywebview.api) {
        callApi("chat_message", userMsg.text, currentSessionId);
      } else {
        // Mock fallback
        setTimeout(() => {
          window.receiveChatStream("Esta é uma resposta regenerada para o prompt: " + userMsg.text, true, false);
          window.receiveChatStream("", false, true);
        }, 1000);
      }
    } catch (err) {
      console.error("Erro ao regenerar mensagem:", err);
      setIsThinking(false);
    }
  }, [currentSessionId, callApi, setMessages]);

  // Streaming bridge logic
  // Chunks chegam em rajada; acumulamos num ref e damos 1 setMessages por frame
  // (antes: 1 re-render + re-parse markdown por chunk).
  useEffect(() => {
    let pending = "";
    let rafId = null;

    const flush = () => {
      rafId = null;
      if (!pending) return;
      const text = pending;
      pending = "";
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === "streaming-msg" ? { ...msg, text: msg.text + text } : msg,
        ),
      );
    };

    window.receiveChatStream = (chunk, isFirst, isDone) => {
      if (isDone) {
        if (rafId !== null) cancelAnimationFrame(rafId);
        flush();
        setIsThinking(false);
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === "streaming-msg" ? { ...msg, id: Date.now() } : msg,
          ),
        );
        // Atualiza a sidebar assim que a resposta completa do JARVIS estiver gravada no SQLite
        fetchRecentSessions();
        return;
      }
      if (isFirst) {
        if (rafId !== null) cancelAnimationFrame(rafId);
        pending = "";
        rafId = null;
        setIsThinking(false);
        setMessages((prev) => [
          ...prev,
          {
            id: "streaming-msg",
            sender: "jarvis",
            text: chunk,
            time: new Date().toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            }),
          },
        ]);
      } else {
        pending += chunk;
        if (rafId === null) rafId = requestAnimationFrame(flush);
      }
    };
    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      delete window.receiveChatStream;
    };
  }, [setMessages, fetchRecentSessions]);

  // File attach handlers — lê o File real (base64) em vez de descartá-lo,
  // pra imagem virar preview + payload enviável e áudio virar transcrição.
  const processFiles = useCallback((fileList) => {
    const files = Array.from(fileList || []);
    files.forEach((file) => {
      const isImage = file.type.startsWith("image/");
      const isAudio = file.type.startsWith("audio/");
      if (!isImage && !isAudio) return; // tipo não suportado por esta feature — ignora

      const { icon, glow } = getFileStyle(file);
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = reader.result;
        const base64 = typeof dataUrl === "string" ? dataUrl.split(",")[1] : null;
        setAttachedFiles((prev) => [
          ...prev,
          {
            id: Date.now() + Math.random(),
            name: file.name,
            icon,
            glow,
            mime: file.type,
            kind: isImage ? "image" : "audio",
            base64,
            previewUrl: isImage ? dataUrl : null,
          },
        ]);
      };
      reader.readAsDataURL(file);
    });
  }, []);

  const handleFileChange = (e) => {
    processFiles(e.target.files);
    e.target.value = "";
  };

  const handleRemoveFile = (id) =>
    setAttachedFiles((prev) => prev.filter((f) => f.id !== id));

  // Send message handler
  const handleSend = async (textToSend) => {
    const text = textToSend || inputValue;
    if (!text.trim() && attachedFiles.length === 0) return;

    const audios = attachedFiles.filter((f) => f.kind === "audio");
    const images = attachedFiles.filter((f) => f.kind === "image");

    // Áudio sempre intercepta o envio: vira transcrição na caixa de texto,
    // nunca entra direto na pipeline de chat/LLM (mesmo com texto já digitado).
    if (audios.length > 0) {
      const audio = audios[0];
      setAttachedFiles((prev) => prev.filter((f) => f.kind !== "audio"));
      setIsThinking(true);
      try {
        const result = await callApi("transcribe_audio", audio.base64, audio.mime, audio.name);
        if (result?.success) {
          setInputValue((prev) => (prev.trim() ? `${prev.trim()} ${result.text}` : result.text));
        } else {
          console.error("Falha na transcrição de áudio:", result?.error);
        }
      } catch (err) {
        console.error("Erro ao transcrever áudio:", err);
      } finally {
        setIsThinking(false);
      }
      return;
    }

    const userMessage = {
      id: Date.now(),
      sender: "user",
      text: text,
      attachments: images.length > 0 ? [...images] : undefined,
      time: new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue("");
    setAttachedFiles([]);
    setIsThinking(true);

    if (window.pywebview && window.pywebview.api) {
      // Passa a mensagem de texto acompanhada da chave de sessão ativa e das imagens anexadas
      const imagePayload = images.length
        ? images.map((f) => ({ mime: f.mime, data: f.base64, name: f.name }))
        : null;
      callApi("chat_message", text, currentSessionId, imagePayload);
      // Atualiza a sidebar de sessões recentes com pequeno atraso para registrar o título (primeiro prompt)
      setTimeout(fetchRecentSessions, 150);
    } else {
      // Mock Fallback local
      setTimeout(() => {
        let responseText =
          "Entendido, Felipe. Processando comando e sincronizando rotinas com o Obsidian Vault.";
        if (
          text.toLowerCase().includes("code") ||
          text.toLowerCase().includes("código")
        )
          responseText =
            "Roteiro de código gerado e indexado na árvore do projeto. Deseja realizar o deploy local ou rodar os testes de integridade?";
        else if (
          text.toLowerCase().includes("status") ||
          text.toLowerCase().includes("telemetria")
        )
          responseText =
            "Telemetria operacional. Todos os núcleos térmicos e pipelines de rede estão operando estavelmente (Ping: 4ms).";

        const words = responseText.split(" ");
        let idx = 0;
        const intervalId = setInterval(() => {
          if (idx === 0)
            window.receiveChatStream(words[idx] + " ", true, false);
          else if (idx < words.length)
            window.receiveChatStream(words[idx] + " ", false, false);
          else {
            clearInterval(intervalId);
            window.receiveChatStream("", false, true);
          }
          idx++;
        }, 80);
      }, 1000);
    }
  };

  return (
    <div className="w-full flex-1 min-h-0 flex relative overflow-hidden bg-transparent">
      {/* ── SIDEBAR ─────────────────────────────────────────────────────── */}
      <ChatSidebar
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        onRenameSession={handleRenameSession}
        onTogglePin={handleTogglePin}
        recentSessions={recentSessions}
        currentSessionId={currentSessionId}
      />

      {/* ── MAIN CHAT AREA ───────────────────────────────────────────────── */}
      <main className="flex-1 h-full flex flex-col justify-between items-center relative overflow-hidden z-30 pt-16 px-6">
        <MessageList
          messages={messages}
          isThinking={isThinking}
          onEditMessage={handleEditMessage}
          onRegenerateMessage={handleRegenerateMessage}
        />

        {/* ── INPUT AREA ──────────────────────────────────────────────────── */}
        <ChatInput
          inputValue={inputValue}
          setInputValue={setInputValue}
          attachedFiles={attachedFiles}
          onFileChange={handleFileChange}
          onFilesDropped={processFiles}
          onRemoveFile={handleRemoveFile}
          onSend={handleSend}
        />
      </main>
    </div>
  );
}
