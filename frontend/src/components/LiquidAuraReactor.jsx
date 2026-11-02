import { memo, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  generateParticles3D,
  generateCoreParticles3D,
} from "./CORE/ReactorMath";

// Cor (r,g,b) e escala por estado. Constantes de módulo: sem alocação por render.
const THEMES = {
  critical: { rgb: "255, 70, 70", scale: 1.15 },
  listening: { rgb: "255, 255, 255", scale: 1.1 }, // React listening = Python PROCESSING
  processing: { rgb: "160, 120, 255", scale: 1.05 },
  speaking: { rgb: "0, 240, 255", scale: 1.2 },
  idle: { rgb: "0, 188, 255", scale: 1.0 },
};

const SIZE = 400;
const FOCAL = 280;
const TILT = 0.35;
const COS_TILT = Math.cos(TILT);
const SIN_TILT = Math.sin(TILT);

// Idle quase não se move: 10fps basta. Ativo: 30fps.
const FRAME_MS_IDLE = 100;
const FRAME_MS_ACTIVE = 33;

function LiquidAuraReactor({
  state = "idle",
  isCritical = false,
  activeMode = "talk",
  hasMessages = false,
}) {
  const canvasRef = useRef(null);
  const [particles] = useState(() => [
    ...generateParticles3D(70),
    ...generateCoreParticles3D(70, 45),
  ]);

  const theme = isCritical ? THEMES.critical : (THEMES[state] ?? THEMES.idle);
  const paused = activeMode === "chat" && hasMessages; // orbe escondido: nem desenha

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || paused) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = SIZE * dpr;
    canvas.height = SIZE * dpr;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);

    const rgb = theme.rgb;
    const frameMs = state === "idle" ? FRAME_MS_IDLE : FRAME_MS_ACTIVE;
    const half = SIZE / 2;
    const speed = state === "speaking" ? 1.2 : state === "listening" ? 0.1 : 0;

    let rafId = 0;
    let last = 0;
    let t = 0;

    const draw = () => {
      ctx.clearRect(0, 0, SIZE, SIZE);

      // Anel externo, levemente distorcido quando falando
      ctx.beginPath();
      ctx.lineWidth = 0.8;
      ctx.strokeStyle = `rgba(${rgb}, ${state === "speaking" ? 0.3 : 0.15})`;
      const amp = state === "speaking" ? 10 : 2;
      for (let i = 0; i <= 64; i++) {
        const a = (i * 2 * Math.PI) / 64;
        const r = 75 + Math.sin(a * 5 + t * 0.1) * amp;
        const x = half + r * Math.cos(a);
        const y = half + r * Math.sin(a);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();

      // Partículas: projeção 3D e desenho (1 arco por partícula)
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        p.currentAngle += p.orbitSpeed * speed;
        const ang = p.currentAngle;

        let rScale = 1;
        let opacity = 0.4 + Math.sin(t * 0.05 + p.phase) * 0.25;
        if (state === "speaking") {
          rScale += Math.sin(t * 0.18 + p.phase) * 0.3 * p.reactiveFactor;
          opacity = 0.7 + Math.sin(t * 0.1 + p.phase) * 0.3;
        } else if (state === "idle" && p.isCore) {
          opacity = 0.6;
        }

        const x3 = p.x3d * rScale;
        const y3 = p.y3d * rScale;
        const z3 = p.z3d * rScale;
        const x1 = x3 * Math.cos(ang) - z3 * Math.sin(ang);
        const z1 = x3 * Math.sin(ang) + z3 * Math.cos(ang);
        const y2 = y3 * COS_TILT - z1 * SIN_TILT;
        const z2 = y3 * SIN_TILT + z1 * COS_TILT;
        const s = FOCAL / (FOCAL + z2);

        // Fundo da esfera mais apagado
        const a = z2 > 0 ? opacity * 0.6 : opacity;
        ctx.beginPath();
        ctx.arc(half + x1 * s, half + y2 * s, p.size * s * 1.4, 0, 2 * Math.PI);
        ctx.fillStyle = `rgba(${rgb}, ${(a * 0.85).toFixed(2)})`;
        ctx.fill();
      }
      t += frameMs / 16.7;
    };

    const loop = (now) => {
      rafId = requestAnimationFrame(loop);
      if (document.hidden || now - last < frameMs) return;
      last = now;
      draw();
    };
    rafId = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafId);
  }, [state, theme, particles, paused]);

  return (
    <div className="relative flex items-center justify-center w-[500px] h-[500px] select-none pointer-events-none">
      {/* Núcleo: gradiente radial simples, sem blur/backdrop */}
      <motion.div
        animate={{ scale: theme.scale }}
        transition={{ type: "spring", stiffness: 140, damping: 16 }}
        className="absolute rounded-full"
        style={{
          width: 130,
          height: 130,
          background: `radial-gradient(circle at 35% 35%, rgba(${theme.rgb}, 0.35) 0%, rgba(${theme.rgb}, 0.05) 70%, transparent 100%)`,
          border: `1px solid rgba(${theme.rgb}, 0.25)`,
        }}
      />
      {!paused && (
        <canvas
          ref={canvasRef}
          style={{ width: SIZE, height: SIZE }}
          className="absolute"
        />
      )}
    </div>
  );
}

export default memo(LiquidAuraReactor);
