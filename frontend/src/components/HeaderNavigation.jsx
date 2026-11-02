import { motion } from "framer-motion";
import { TalkIcon, ChatIcon } from "./CORE/NavIcons";

const handleClose = () => {
  if (window.pywebview?.api) window.pywebview.api.shutdown();
};
const handleMinimize = () => {
  if (window.pywebview?.api) window.pywebview.api.minimize();
};
const handleMaximize = () => {
  if (window.pywebview?.api) window.pywebview.api.toggle_maximize();
};

const MODE_ACCENTS = {
  talk: {
    color: "rgba(0, 188, 255, 1)",
    bg: "rgba(0, 188, 255, 0.18)",
    border: "rgba(0, 188, 255, 0.3)",
    glow: "rgba(0, 188, 255, 0.4)",
    bgBubble: "rgba(0, 188, 255, 0.07)",
  },
  chat: {
    color: "rgba(150, 100, 255, 1)",
    bg: "rgba(130, 80, 255, 0.2)",
    border: "rgba(130, 80, 255, 0.35)",
    glow: "rgba(130, 80, 255, 0.4)",
    bgBubble: "rgba(130, 80, 255, 0.08)",
  },
};

const CRITICAL_ACCENT = {
  color: "#ff453a",
  bg: "rgba(255, 59, 48, 0.22)",
  border: "rgba(255, 59, 48, 0.35)",
  glow: "rgba(255, 59, 48, 0.45)",
  bgBubble: "rgba(255, 59, 48, 0.08)",
};

export default function HeaderNavigation({
  activeMode,
  setActiveMode,
  isCritical,
}) {
  const tabs = [
    { id: "talk", label: "Copilot", icon: <TalkIcon /> },
    { id: "chat", label: "Chat", icon: <ChatIcon /> },
  ];

  const getTabAccent = (tabId) => {
    if (isCritical) return CRITICAL_ACCENT;
    return MODE_ACCENTS[tabId] ?? MODE_ACCENTS.talk;
  };

  return (
    <>
      {/* Drag bar — full width transparent strip at top, enables window dragging */}
      <div
        className="fixed top-0 left-0 right-0 h-10 z-[999] pointer-events-auto"
        style={{ WebkitAppRegion: "drag" }}
      >
        {/* Window controls — top-right, no-drag so they stay clickable */}
        <div
          className="absolute right-4 top-1/2 -translate-y-1/2 flex items-center gap-[7px]"
          style={{ WebkitAppRegion: "no-drag" }}
        >
          <button
            onClick={handleClose}
            title="Fechar"
            className="w-[10px] h-[10px] rounded-full bg-[#ff5f57] hover:brightness-125 transition-all cursor-pointer opacity-80 hover:opacity-100"
          />
          <button
            onClick={handleMinimize}
            title="Minimizar"
            className="w-[10px] h-[10px] rounded-full bg-[#ffbd2e] hover:brightness-125 transition-all cursor-pointer opacity-80 hover:opacity-100"
          />
          <button
            onClick={handleMaximize}
            title="Maximizar / Restaurar"
            className="w-[10px] h-[10px] rounded-full bg-[#28c940] hover:brightness-125 transition-all cursor-pointer opacity-80 hover:opacity-100"
          />
        </div>
      </div>

      {/* Tab pill — centered, tabs only */}
      <motion.header
        initial={{ y: -60, x: "-50%", opacity: 0 }}
        animate={{ y: 0, x: "-50%", opacity: 1 }}
        transition={{ type: "spring", stiffness: 100, damping: 18, delay: 0.2 }}
        className="fixed top-10 left-1/2 z-[100] flex items-center justify-center select-none pointer-events-auto"
      >
        <div
          style={{
            background: "rgba(15, 15, 20, 0.7)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "26px",
          }}
          className="relative flex items-center gap-1.5 p-2"
        >
          {tabs.map((tab) => {
            const isActive = activeMode === tab.id;
            const accent = getTabAccent(tab.id);
            return (
              <motion.button
                key={tab.id}
                onClick={() => setActiveMode(tab.id)}
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.96 }}
                style={{
                  WebkitAppRegion: "no-drag",
                  color: isActive ? accent.color : undefined,
                }}
                className={`relative px-7 py-2.5 text-[11px] font-bold uppercase tracking-[0.16em] rounded-[18px] transition-colors duration-300 cursor-pointer flex items-center justify-center group ${
                  isActive ? "" : "text-white/40 hover:text-white/80"
                }`}
              >
                {isActive && (
                  <motion.div
                    layoutId="activeHeaderTab"
                    transition={{ type: "spring", stiffness: 280, damping: 26 }}
                    style={{
                      background: `linear-gradient(135deg, ${accent.bg} 0%, ${accent.bgBubble} 100%)`,
                      border: `1px solid ${accent.border}`,
                    }}
                    className="absolute inset-0 rounded-[18px] -z-10"
                  />
                )}
                <span className="relative z-10 flex items-center justify-center">
                  {tab.icon}
                  <span className="mt-[0.5px]">{tab.label}</span>
                </span>
              </motion.button>
            );
          })}
        </div>
      </motion.header>
    </>
  );
}
