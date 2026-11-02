import { motion } from "framer-motion";

export default function FileChip({ file, onRemove }) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.75, y: 6 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.75, y: 6 }}
      transition={{ type: "spring", stiffness: 260, damping: 22 }}
      className="flex items-center gap-1.5 px-2.5 py-1.5 text-[10px] text-white/80 select-none"
      style={{
        background: `linear-gradient(135deg, rgba(${file.glow},0.14), rgba(${file.glow},0.22))`,
        boxShadow: `0 4px 12px rgba(${file.glow},0.2), 0 1px 4px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.1)`,
        border: `1px solid rgba(${file.glow},0.28)`,
        borderRadius: "12px",
      }}
    >
      <span className="text-[11px]">{file.icon}</span>
      <span className="max-w-[110px] truncate">{file.name}</span>
      <button
        onClick={() => onRemove(file.id)}
        className="ml-0.5 w-3.5 h-3.5 rounded-full flex items-center justify-center text-white/35 hover:text-white/80 transition-colors leading-none"
        style={{ fontSize: "13px", lineHeight: 1 }}
      >
        ×
      </button>
    </motion.div>
  );
}
