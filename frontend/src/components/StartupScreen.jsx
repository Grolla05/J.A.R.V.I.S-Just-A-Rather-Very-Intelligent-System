import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

const BOOT_SEQUENCE = [
  "Initializing neural core...",
  "Loading language models...",
  "Calibrating voice synthesis...",
  "Establishing secure bridge...",
  "Mounting skill modules...",
  "All systems nominal.",
];

export default function StartupScreen({ onComplete }) {
  const [progress, setProgress] = useState(0);

  // Derivado do progresso durante o render: nao precisa de state + efeito.
  const currentLine = Math.min(
    Math.floor((progress / 100) * BOOT_SEQUENCE.length),
    BOOT_SEQUENCE.length - 1,
  );

  useEffect(() => {
    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval);
          setTimeout(onComplete, 900);
          return 100;
        }
        const jump = Math.random() > 0.8 ? 12 : 2;
        return Math.min(prev + jump, 100);
      });
    }, 100);
    return () => clearInterval(interval);
  }, [onComplete]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      className="fixed inset-0 z-[100] flex flex-col items-center justify-center overflow-hidden"
      style={{ background: "rgba(8, 8, 12, 0.98)" }}
    >
      {/* Glass card */}
      <motion.div
        initial={{ opacity: 0, scale: 0.93, y: 18 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: "spring", stiffness: 100, damping: 20, delay: 0.1 }}
        style={{
          background: "rgba(15, 15, 20, 0.6)",
          border: "1px solid rgba(255, 255, 255, 0.08)",
          borderRadius: "28px",
        }}
        className="relative flex flex-col items-center px-16 py-14 w-[460px]"
      >
        {/* Logo */}
        <div className="mb-10 text-center select-none">
          <motion.h1
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25, type: "spring", stiffness: 120, damping: 18 }}
            className="text-5xl font-bold tracking-[0.25em] text-white"
          >
            J.A.R.V.I.S.
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.45 }}
            className="text-[11px] font-semibold uppercase tracking-[0.55em] mt-2"
            style={{ color: "rgba(255,255,255,0.25)" }}
          >
            System v1.0
          </motion.p>
        </div>

        {/* Boot log line */}
        <div className="w-full mb-8 h-5 flex items-center">
          <AnimatePresence mode="wait">
            <motion.p
              key={currentLine}
              initial={{ opacity: 0, x: -5 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="text-[11px] font-mono tracking-wide"
              style={{ color: "rgba(0, 188, 255, 0.5)" }}
            >
              {BOOT_SEQUENCE[currentLine]}
            </motion.p>
          </AnimatePresence>
        </div>

        {/* Progress */}
        <div className="w-full">
          <div className="flex justify-between items-center mb-2">
            <span
              className="text-[10px] uppercase tracking-[0.22em] font-semibold"
              style={{ color: "rgba(255,255,255,0.2)" }}
            >
              Loading
            </span>
            <span
              className="text-[10px] tabular-nums font-semibold"
              style={{ color: "rgba(255,255,255,0.2)" }}
            >
              {Math.floor(progress)}%
            </span>
          </div>

          <div
            className="h-[2px] w-full rounded-full overflow-hidden"
            style={{ background: "rgba(255,255,255,0.05)" }}
          >
            <motion.div
              className="h-full rounded-full"
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.12, ease: "easeOut" }}
              style={{
                background: "rgba(0, 200, 255, 0.9)",
              }}
            />
          </div>
        </div>
      </motion.div>

      {/* Footer */}
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.7 }}
        className="absolute bottom-10 text-[10px] uppercase tracking-[0.3em] font-medium select-none"
        style={{ color: "rgba(255,255,255,0.12)" }}
      >
        Stark Industries · Autonomous Assistant
      </motion.p>
    </motion.div>
  );
}
