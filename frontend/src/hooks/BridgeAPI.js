import { useState, useEffect, useCallback } from "react";

export default function useBridgeAPI() {
  const [isReady, setIsReady] = useState(
    !!(window.pywebview && window.pywebview.api),
  );

  useEffect(() => {
    if (isReady) return;

    const handleReady = () => {
      setIsReady(true);
    };

    window.addEventListener("pywebviewready", handleReady);
    return () => window.removeEventListener("pywebviewready", handleReady);
  }, [isReady]);

  // Identidade estável: `callApi` só depende de `window`, então pode entrar nos
  // arrays de dependência dos consumidores sem re-disparar efeitos a cada render.
  const callApi = useCallback(async (method, ...args) => {
    if (window.pywebview && window.pywebview.api) {
      if (typeof window.pywebview.api[method] === "function") {
        try {
          return await window.pywebview.api[method](...args);
        } catch (err) {
          console.error(`[BridgeAPI ERR] Failed calling ${method}:`, err);
          throw err;
        }
      }
    }

    // Local mock simulations fallback for easy web testing
    return getMockFallback(method, ...args);
  }, []);

  return { isReady, callApi };
}

// Fallback resolver for local dashboard previews
function getMockFallback(method, ...args) {
  console.warn(`[BridgeAPI MOCK] Fallback preview for API method: "${method}"`);
  if (method === "get_skills") {
    return [
      {
        id: "automation",
        label: "Automation",
        icon: "⚡",
        enabled: true,
        skills: [
          {
            id: "APP_CONTROL",
            name: "App Control",
            desc: "Abre e fecha janelas de softwares localmente.",
            fileName: "app_control.py",
            enabled: true,
            categoryEnabled: true,
          },
          {
            id: "KEYBOARD_CONTROL",
            name: "Keyboard",
            desc: "Simula atalhos e inserções de teclas físicas.",
            fileName: "keyboard.py",
            enabled: true,
            categoryEnabled: true,
          },
        ],
      },
      {
        id: "system",
        label: "System",
        icon: "⚙️",
        enabled: true,
        skills: [
          {
            id: "SYSTEM_REPORT",
            name: "System Diagnostic",
            desc: "Diagnóstico profundo térmico e de consumo.",
            fileName: "status_report.py",
            enabled: true,
            categoryEnabled: true,
          },
        ],
      },
    ];
  }
  if (method === "get_telemetry") {
    return {
      cpu: { usage: Math.floor(15 + Math.random() * 20) },
      ram: { used_gb: (2.2 + Math.random() * 0.5).toFixed(1) },
      net: { download_speed: "34.2 MB/s", upload_speed: "6.1 MB/s" },
      battery: { percent: 92 },
      sys: { uptime: "02:14:35" },
    };
  }
  if (method === "get_recent_sessions") {
    return [
      { id: "mock_session_1", title: "Organizar documentação de feature no Obsidian", is_pinned: true },
      { id: "mock_session_2", title: "Atualizar sistema de tags do Obsidian", is_pinned: false },
      { id: "mock_session_3", title: "Conectar Claude ao Obsidian via API", is_pinned: false }
    ];
  }
  if (method === "update_session_title") {
    console.log(`[BridgeAPI MOCK] Renomear sessão '${args[0]}' para: '${args[1]}'`);
    return true;
  }
  if (method === "toggle_session_pin") {
    console.log(`[BridgeAPI MOCK] Alternar fixação da sessão '${args[0]}' para: ${args[1]}`);
    return true;
  }
  if (method === "get_chat_history") {
    return [
      { id: 1, sender: "user", text: "Olá JARVIS, mostre meu status.", time: "17:15" },
      { id: 2, sender: "jarvis", text: "Olá Senhor. Telemetria nominal (Ping: 4ms). Todos os núcleos de Stark Industries estão operando perfeitamente.", time: "17:15" }
    ];
  }
  if (method === "transcribe_audio") {
    return { success: true, text: "[MOCK] Transcrição simulada do áudio anexado." };
  }
  return null;
}
