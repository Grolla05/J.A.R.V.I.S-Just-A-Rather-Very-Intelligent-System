import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import TelemetryWidget from "./TELEMETRY/TelemetryWidget";
import CpuRamWidget from "./TELEMETRY/CpuRamWidget";
import useBridgeAPI from "../hooks/BridgeAPI";

export default function LiveTelemetry() {
  const [data, setData] = useState(null);
  const [showCpuWidget, setShowCpuWidget] = useState(true);
  const { isReady, callApi } = useBridgeAPI();

  // Telemetria via PUSH: o Python chama window.receiveTelemetry só quando há
  // mudança relevante (delta-gated), eliminando o polling de 1s.
  useEffect(() => {
    // Bridge real → registra o ouvinte de push
    window.receiveTelemetry = (payload) => {
      if (payload) setData(payload);
    };

    // Fetch inicial único: evita widget em branco até o 1º push.
    callApi("get_telemetry")
      .then((stats) => stats && setData(stats))
      .catch((err) => console.error("Erro no fetch inicial de telemetria:", err));

    // Modo mock (browser dev, sem pywebview): não há push → mantém polling local.
    let mockInterval = null;
    if (!isReady) {
      mockInterval = setInterval(async () => {
        const stats = await callApi("get_telemetry");
        if (stats) setData(stats);
      }, 1000);
    }

    return () => {
      delete window.receiveTelemetry;
      if (mockInterval) clearInterval(mockInterval);
    };
  }, [isReady, callApi]);

  if (!data) return null;

  return (
    <div className="absolute inset-0 pointer-events-none z-40 overflow-hidden">
      {/* Quick widget restoration triggers in the footer */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-3 pointer-events-auto select-none opacity-45 hover:opacity-100 transition-opacity duration-300">
        {!showCpuWidget && (
          <motion.button
            onClick={() => setShowCpuWidget(true)}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="px-3 py-1 rounded-full bg-black/40 border border-white/5 text-[8px] font-bold tracking-widest uppercase text-cyan-400 cursor-pointer"
          >
            + Core Diagnostic
          </motion.button>
        )}
      </div>

      {/* CORE DIAGNOSTIC WIDGET */}
      <AnimatePresence>
        {showCpuWidget && (
          <TelemetryWidget
            title="Core Diagnostics"
            onClose={() => setShowCpuWidget(false)}
            positionClasses="bottom-10 left-10"
          >
            <CpuRamWidget data={data} />
          </TelemetryWidget>
        )}
      </AnimatePresence>
    </div>
  );
}
