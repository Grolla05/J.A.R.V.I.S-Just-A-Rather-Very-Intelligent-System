import { motion } from "framer-motion";
import FileChip from "./FileChip";

// Preview real (thumbnail) pra anexos de imagem — o ponto da feature é
// confirmação visual do que foi analisado, não só um chip com o nome do
// arquivo. Áudio (e qualquer outro tipo) cai pro FileChip existente, já que
// vira só texto transcrito, não fica como artefato reproduzível no chat.
export default function AttachmentPreview({ file, onRemove }) {
  const src = file.kind === "image" ? file.previewUrl || (file.base64 ? `data:${file.mime};base64,${file.base64}` : null) : null;

  if (file.kind === "image" && src) {
    return (
      <motion.div
        layout
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
        transition={{ type: "spring", stiffness: 260, damping: 24 }}
        className="relative"
      >
        <img
          src={src}
          alt={file.name}
          className="max-w-[220px] max-h-[220px] rounded-xl object-cover"
          style={{ border: "1px solid rgba(255,255,255,0.08)" }}
        />
        {onRemove && (
          <button
            onClick={() => onRemove(file.id)}
            className="absolute top-1.5 right-1.5 w-5 h-5 rounded-full flex items-center justify-center text-white/70 hover:text-white transition-colors leading-none"
            style={{ background: "rgba(0,0,0,0.55)", fontSize: "13px" }}
          >
            ×
          </button>
        )}
      </motion.div>
    );
  }

  return <FileChip file={file} onRemove={onRemove} />;
}
