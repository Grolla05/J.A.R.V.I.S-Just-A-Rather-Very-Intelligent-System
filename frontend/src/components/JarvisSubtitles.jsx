import { motion, AnimatePresence } from "framer-motion";

export default function JarvisSubtitles({ jarvisState, isCritical, text }) {
  // Cores dinâmicas para o visualizador e texto de destaque
  const getThemeColors = () => {
    if (isCritical) {
      return {
        accent: "text-red-500",
        border: "border-red-500/20",
        bg: "bg-red-950/10",
        glow: "shadow-[0_0_15px_rgba(239,68,68,0.15)]",
        waveBg: "bg-red-500",
      };
    }
    switch (jarvisState) {
      case "listening": // "Processing" no Python (Roxo)
        return {
          accent: "text-purple-400",
          border: "border-purple-500/20",
          bg: "bg-purple-950/10",
          glow: "shadow-[0_0_15px_rgba(168,85,247,0.15)]",
          waveBg: "bg-purple-400",
        };
      case "speaking": // "Speaking" no Python (Cyan)
        return {
          accent: "text-cyan-400",
          border: "border-cyan-500/25",
          bg: "bg-cyan-950/10",
          glow: "shadow-[0_0_15px_rgba(34,211,238,0.2)]",
          waveBg: "bg-cyan-400",
        };
      case "idle":
      default:
        return {
          accent: "text-cyan-400/80",
          border: "border-white/5",
          bg: "bg-white/[0.01]",
          glow: "shadow-[0_10px_30px_rgba(0,0,0,0.2)]",
          waveBg: "bg-cyan-500/50",
        };
    }
  };

  const theme = getThemeColors();

  // Se estiver falado, mostra o equalizador animado
  const renderEqualizer = () => {
    if (jarvisState !== "speaking") return null;

    const bars = [1, 2, 3, 4, 5];
    return (
      <div className="flex items-center gap-0.5 h-3 ml-2.5">
        {bars.map((bar, idx) => (
          <motion.div
            key={idx}
            className={`w-0.5 rounded-full ${theme.waveBg}`}
            animate={{
              height: [4, 12, 6, 14, 4][idx % 5] ? [4, 12, 4] : [4, 10, 4],
            }}
            transition={{
              duration: 0.6 + idx * 0.1,
              repeat: Infinity,
              ease: "easeInOut",
            }}
            style={{ height: 4 }}
          />
        ))}
      </div>
    );
  };

  // Texto amigável baseado no estado se o texto real for vazio
  const getDisplayText = () => {
    if (text && text.trim() !== "") return text;
    if (isCritical) return "ALERTA CRÍTICO: Sistemas em sobrecarga ou anomalia detectada.";
    if (jarvisState === "listening") return "Processando requisição neurológica...";
    return "Sistemas em Standby. Aguardando comando de voz...";
  };

  const displayTxt = getDisplayText();

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 100, damping: 20 }}
      className="w-full max-w-xl px-4 z-40"
    >
      <div
        className={`w-full p-5 rounded-2xl border ${theme.border} ${theme.bg} ${theme.glow} transition-all duration-500 flex flex-col gap-2.5 relative overflow-hidden`}
      >
        {/* Glow interno sutil */}
        <div className="absolute inset-0 bg-gradient-to-b from-white/[0.02] to-transparent pointer-events-none" />

        {/* Linha de topo: Status e Identificador */}
        <div className="flex items-center justify-between border-b border-white/5 pb-2.5 select-none">
          <div className="flex items-center">
            <span className={`text-[10px] font-bold tracking-[0.2em] uppercase ${theme.accent}`}>
              J.A.R.V.I.S.
            </span>
            {renderEqualizer()}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[9px] font-medium text-white/40 uppercase tracking-widest">
              Live Link
            </span>
          </div>
        </div>

        {/* Corpo de Legenda com Transição Fluida de Texto */}
        <div className="min-h-11 flex items-center justify-center py-1">
          <AnimatePresence mode="wait">
            <motion.p
              key={displayTxt}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ type: "spring", stiffness: 140, damping: 15 }}
              className="text-sm font-medium text-white/90 text-center leading-relaxed tracking-wide select-text"
            >
              {displayTxt}
            </motion.p>
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}
