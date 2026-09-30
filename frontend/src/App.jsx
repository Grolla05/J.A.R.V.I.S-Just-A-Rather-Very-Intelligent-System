import { lazy, Suspense, useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import LiquidAuraReactor from "./components/LiquidAuraReactor";
import StartupScreen from "./components/StartupScreen";
import LiveTelemetry from "./components/LiveTelemetry";
import HeaderNavigation from "./components/HeaderNavigation";
import JarvisSubtitles from "./components/JarvisSubtitles";
import SkillsSidebar from "./components/SkillsSidebar";
import useBridgeAPI from "./hooks/BridgeAPI";

// Chat carrega markdown + KaTeX (~260KB): só entra quando o usuário abre o modo chat
const ChatPanel = lazy(() => import("./components/ChatPanel"));

export default function App() {
  // phase: 'loading' | 'active'
  const [phase, setPhase] = useState("loading");
  const [jarvisState, setJarvisState] = useState("idle");
  const [isCritical, setIsCritical] = useState(false);
  const [activeMode, setActiveMode] = useState("talk"); // talk, chat
  const [subtitlesText, setSubtitlesText] = useState("");
  const [chatMessages, setChatMessages] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [isCentering, setIsCentering] = useState(false);
  const centeringTimerRef = useRef(null);
  const { callApi } = useBridgeAPI();
  // Boolean estável durante o stream: o orb só re-renderiza quando isso vira true/false
  const hasMessages = chatMessages.length > 0;
  const orbHidden = activeMode === "chat" && hasMessages;

  // Descarta o timer de recentralização se o App desmontar no meio do pulso
  useEffect(() => () => clearTimeout(centeringTimerRef.current), []);

  useEffect(() => {
    // OUVINTE DE ESTADO (Voz/Processamento)
    window.receiveStatus = (status, text) => {
      let visualState = status.toLowerCase();

      if (visualState === "listening") visualState = "idle";
      else if (visualState === "processing") visualState = "listening";
      else if (visualState === "error") visualState = "idle";

      setJarvisState(visualState);
      if (text !== undefined) {
        setSubtitlesText(text);
      }
    };

    // OUVINTE DE HUD (Sensores/Alerta Vermelho)
    window.updateHudState = (isActive) => setIsCritical(isActive);

    return () => {
      delete window.receiveStatus;
      delete window.updateHudState;
    };
  }, []);

  // Fim do boot: entra direto no modo talk (mic + saudação tratados pelo backend)
  const handleBootComplete = useCallback(() => {
    setPhase("active");
    callApi("on_initial_mode_selected", "talk");
  }, [callApi]);

  // Troca de modo pela navegação superior. O pulso de recentralização nasce
  // aqui, no handler, em vez de um efeito reagindo a activeMode — evita o
  // setState síncrono dentro do efeito (cascading render).
  const handleModeChange = useCallback(
    (modeId) => {
      setActiveMode(modeId);
      setIsCentering(true);
      clearTimeout(centeringTimerRef.current);
      centeringTimerRef.current = setTimeout(() => setIsCentering(false), 700);
      callApi("set_active_mode", modeId);
    },
    [callApi],
  );

  return (
    <main className="w-screen h-screen bg-transparent overflow-hidden flex flex-col items-center justify-center relative text-white font-sans cursor-default">
      {/* Camada Visual do HUD Crítico */}
      {isCritical && <div className="hud-critical-mode" />}

      <AnimatePresence>
        {phase === "loading" && (
          <StartupScreen key="startup" onComplete={handleBootComplete} />
        )}
      </AnimatePresence>

      {phase === "active" && (
        <>
          <HeaderNavigation
            activeMode={activeMode}
            setActiveMode={handleModeChange}
            isCritical={isCritical}
          />

          {/* Orbe central: talk = centro, chat = deslocado, some quando há mensagens */}
          <motion.div
            transition={{ type: "spring", stiffness: 110, damping: 22 }}
            style={{ x: "-50%", y: "-50%" }}
            animate={{
              opacity: orbHidden ? 0 : 1,
              scale: isCentering ? 1.15 : orbHidden ? 0.3 : 1,
            }}
            className={`absolute z-50 pointer-events-none ${
              isCentering
                ? "top-1/2 left-1/2 mt-[-100px]"
                : activeMode === "talk"
                  ? "top-1/2 left-1/2 mt-[-60px]"
                  : "top-1/2 left-[calc(50%+125px)] mt-[-120px]"
            }`}
          >
            <LiquidAuraReactor
              state={jarvisState}
              isCritical={isCritical}
              activeMode={activeMode}
              hasMessages={hasMessages}
            />
          </motion.div>

          {activeMode === "chat" ? (
            <Suspense fallback={null}>
              <ChatPanel
                messages={chatMessages}
                setMessages={setChatMessages}
                currentSessionId={currentSessionId}
                setCurrentSessionId={setCurrentSessionId}
              />
            </Suspense>
          ) : (
            <>
              <SkillsSidebar isCritical={isCritical} />

              <div className="absolute bottom-16 left-0 right-0 flex justify-center w-full pointer-events-none z-40">
                <div className="w-full flex justify-center pointer-events-auto px-4">
                  <JarvisSubtitles
                    jarvisState={jarvisState}
                    isCritical={isCritical}
                    text={subtitlesText}
                  />
                </div>
              </div>

              <LiveTelemetry />
            </>
          )}
        </>
      )}
    </main>
  );
}
