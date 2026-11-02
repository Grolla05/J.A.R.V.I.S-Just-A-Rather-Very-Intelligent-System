// Mapeia o MIME type do anexo para ícone e cor de brilho do chip.
// Mora fora de FileChip.jsx para que aquele arquivo exporte só o componente
// e o Fast Refresh continue funcionando.
export const getFileStyle = (file) => {
  const t = file.type;
  if (t.startsWith("image/")) return { icon: "🖼️", glow: "168,85,247" };
  if (t.startsWith("audio/")) return { icon: "🎵", glow: "34,211,238" };
  if (t === "application/pdf") return { icon: "📄", glow: "249,115,22" };
  if (t.startsWith("video/")) return { icon: "🎬", glow: "239,68,68" };
  return { icon: "📁", glow: "34,197,94" };
};
