import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Zap,
  Settings,
  Home,
  Calendar,
  Globe,
  ChevronRight,
} from "lucide-react";
import useBridgeAPI from "../hooks/BridgeAPI";

const getCategoryIcon = (categoryId) => {
  const props = {
    size: 14,
    className:
      "opacity-80 group-hover:scale-110 transition-transform text-cyan-400 shrink-0",
  };
  switch (categoryId) {
    case "automation":
      return <Zap {...props} />;
    case "system":
      return <Settings {...props} />;
    case "IoT":
      return <Home {...props} />;
    case "productivity":
      return <Calendar {...props} />;
    case "web":
      return <Globe {...props} />;
    default:
      return <Settings {...props} />;
  }
};

export default function SkillsSidebar({ isCritical }) {
  const [isOpen, setIsOpen] = useState(false);
  const [expandedCategory, setExpandedCategory] = useState(null);
  const [categories, setCategories] = useState([]);
  const { callApi } = useBridgeAPI();

  // Busca as skills diretamente do backend em tempo real
  useEffect(() => {
    const fetchSkills = async () => {
      try {
        const fetched = await callApi("get_skills");
        if (fetched && fetched.length > 0) {
          setCategories(fetched);
        } else {
          setCategories([]);
        }
      } catch (err) {
        console.error("Erro ao buscar skills do backend:", err);
        setCategories([]);
      }
    };

    // Tenta carregar imediatamente
    fetchSkills();

    // Registra o ouvinte para quando a ponte pywebview estiver pronta
    window.addEventListener("pywebviewready", fetchSkills);

    // Recarrega sempre que a aba for aberta para garantir atualização em tempo real
    if (isOpen) {
      fetchSkills();
    }

    return () => {
      window.removeEventListener("pywebviewready", fetchSkills);
    };
  }, [isOpen, callApi]);

  const toggleSidebar = () => setIsOpen(!isOpen);

  // Liga/Desliga Categoria Completa (Lote/Grupo)
  const handleToggleCategory = async (e, categoryId, currentEnabled) => {
    e.stopPropagation(); // Evita expandir a sanfona ao clicar no switch

    // Atualização local imediata para feedback visual e de mola fluido
    setCategories((prev) =>
      prev.map((cat) =>
        cat.id === categoryId
          ? {
              ...cat,
              enabled: !currentEnabled,
              skills: cat.skills.map((s) => ({
                ...s,
                categoryEnabled: !currentEnabled,
                enabled: !currentEnabled,
              })),
            }
          : cat,
      ),
    );

    try {
      await callApi("toggle_category", categoryId, !currentEnabled);
    } catch (err) {
      console.error(
        `Erro ao alternar ativação da categoria ${categoryId}:`,
        err,
      );
    }
  };

  // Liga/Desliga Habilidade Individual (1 a 1)
  const handleToggleSkill = async (e, skillId, currentEnabled, categoryId) => {
    e.stopPropagation();

    setCategories((prev) =>
      prev.map((cat) =>
        cat.id === categoryId
          ? {
              ...cat,
              skills: cat.skills.map((s) =>
                s.id === skillId ? { ...s, enabled: !currentEnabled } : s,
              ),
            }
          : cat,
      ),
    );

    try {
      await callApi("toggle_skill", skillId, !currentEnabled);
    } catch (err) {
      console.error(`Erro ao alternar ativação da skill ${skillId}:`, err);
    }
  };

  const getThemeColors = () => {
    if (isCritical) {
      return {
        accent: "text-red-400",
        bg: "rgba(20, 10, 10, 0.4)",
        activeTab: "bg-red-500/20 border-red-500/30 text-red-300",
        glow: "shadow-[0_0_15px_rgba(239,68,68,0.1)]",
        toggleOn: "bg-red-500",
        border: "border-red-500/10",
      };
    }
    return {
      accent: "text-cyan-400",
      bg: "rgba(10, 10, 15, 0.4)",
      activeTab: "bg-cyan-500/20 border-cyan-500/30 text-cyan-300",
      glow: "shadow-[0_0_15px_rgba(6,182,212,0.1)]",
      toggleOn: "bg-cyan-400",
      border: "border-white/5",
    };
  };

  const theme = getThemeColors();

  if (categories.length === 0) {
    return null;
  }

  return (
    <>
      {/* Botão de Toggle (Disparador) - Alinhado no Lado Direito */}
      <motion.button
        onClick={toggleSidebar}
        initial={{ x: 20, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        whileHover={{ scale: 1.1, x: -5 }}
        whileTap={{ scale: 0.9 }}
        className="fixed right-6 top-1/2 -translate-y-1/2 z-[60] w-10 h-24 flex items-center justify-center liquid-glass cursor-pointer pointer-events-auto group"
      >
        <div className="flex flex-col gap-1 items-center select-none">
          <div
            className={`w-1 h-1 rounded-full ${isOpen ? "bg-cyan-400" : "bg-white/40"} transition-colors`}
          />
          <span className="[writing-mode:vertical-lr] text-[9px] font-bold tracking-[0.25em] uppercase text-white/60 group-hover:text-cyan-300 transition-colors">
            {isOpen ? "Close" : "Actions"}
          </span>
          <div
            className={`w-1 h-1 rounded-full ${isOpen ? "bg-cyan-400" : "bg-white/40"} transition-colors`}
          />
        </div>
      </motion.button>

      {/* Sidebar Retrátil - Lado Direito */}
      <AnimatePresence>
        {isOpen && (
          <motion.aside
            initial={{ x: 340, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 340, opacity: 0 }}
            transition={{ type: "spring", stiffness: 120, damping: 22 }}
            className="fixed right-0 top-0 bottom-0 w-80 z-[55] p-8 pt-24 pointer-events-auto flex flex-col justify-between"
          >
            <div
              style={{
                background: theme.bg,
                borderLeft: "1px solid rgba(255, 255, 255, 0.08)",
                boxShadow: "-20px 0 50px rgba(0, 0, 0, 0.5)",
              }}
              className="absolute inset-0 -z-10"
            />

            <div className="flex flex-col gap-6 flex-1 overflow-hidden">
              <header className="flex flex-col gap-1 select-none">
                <h2 className="text-xl font-bold tracking-tight text-white/90">
                  Neural Actions
                </h2>
                <p className="text-[10px] uppercase tracking-widest text-cyan-400 font-semibold opacity-60">
                  Subsystem Toggles
                </p>
              </header>

              {/* Lista Dinâmica de Categorias e Toggles */}
              <nav className="flex-1 overflow-y-auto pr-1 flex flex-col gap-3.5 scrollbar-thin">
                {categories.map((cat) => (
                  <div
                    key={cat.id}
                    className={`flex flex-col rounded-2xl border ${theme.border} bg-white/[0.01] overflow-hidden`}
                  >
                    {/* Botão de Categoria Principal com Toggle Switch Integrado */}
                    <div
                      onClick={() =>
                        setExpandedCategory(
                          expandedCategory === cat.id ? null : cat.id,
                        )
                      }
                      className={`flex items-center justify-between p-4 transition-all duration-300 group hover:bg-white/[0.03] cursor-pointer`}
                    >
                      <div className="flex items-center gap-3">
                        {getCategoryIcon(cat.id)}
                        <span
                          className={`text-xs font-semibold tracking-wide transition-all ${cat.enabled ? "text-white" : "text-white/30"}`}
                        >
                          {cat.label}
                        </span>
                      </div>

                      {/* Área de Controle (Toggle Geral + Indicador de Expansão) */}
                      <div className="flex items-center gap-3.5">
                        {/* Switch de Grupo/Categoria */}
                        <button
                          onClick={(e) =>
                            handleToggleCategory(e, cat.id, cat.enabled)
                          }
                          className={`w-8 h-4.5 rounded-full p-0.5 transition-colors duration-300 cursor-pointer flex items-center ${
                            cat.enabled ? theme.toggleOn : "bg-white/10"
                          }`}
                        >
                          <motion.div
                            layout
                            transition={{
                              type: "spring",
                              stiffness: 500,
                              damping: 28,
                            }}
                            className="w-3.5 h-3.5 rounded-full bg-white shadow-md"
                            style={{
                              marginLeft: cat.enabled ? "auto" : "0px",
                            }}
                          />
                        </button>

                        <motion.span
                          animate={{
                            rotate: expandedCategory === cat.id ? 90 : 0,
                          }}
                          className="flex items-center justify-center w-3 h-3 text-white/20"
                        >
                          <ChevronRight size={10} />
                        </motion.span>
                      </div>
                    </div>

                    {/* Subskills Internas (Sanfona) */}
                    <AnimatePresence>
                      {expandedCategory === cat.id && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{
                            type: "spring",
                            stiffness: 180,
                            damping: 20,
                          }}
                          className="border-t border-white/[0.03] bg-black/10 overflow-hidden"
                        >
                          <div className="flex flex-col gap-3.5 p-4 pl-5">
                            {cat.skills.length > 0 ? (
                              cat.skills.map((skill) => {
                                const isSkillActive =
                                  skill.enabled && skill.categoryEnabled;
                                return (
                                  <div
                                    key={skill.id}
                                    className="flex items-start justify-between gap-3 text-[11px] group/item"
                                  >
                                    <div className="flex flex-col gap-0.5 select-text">
                                      <div className="flex items-center gap-1.5">
                                        <span
                                          className={`font-bold transition-all ${isSkillActive ? "text-white/80" : "text-white/20"}`}
                                        >
                                          {skill.name}
                                        </span>
                                        <span className="font-mono text-[7px] opacity-20 group-hover/item:opacity-40 transition-opacity">
                                          {skill.fileName}
                                        </span>
                                      </div>
                                      <span className="text-[9px] text-white/35 leading-relaxed">
                                        {skill.desc}
                                      </span>
                                    </div>

                                    {/* Toggle Switch Individual 1 a 1 */}
                                    <button
                                      onClick={(e) =>
                                        handleToggleSkill(
                                          e,
                                          skill.id,
                                          skill.enabled,
                                          cat.id,
                                        )
                                      }
                                      disabled={!skill.categoryEnabled} // Desabilita se a categoria estiver desligada!
                                      className={`w-7 h-4 rounded-full p-0.5 transition-colors duration-300 flex items-center mt-0.5 ${
                                        !skill.categoryEnabled
                                          ? "bg-white/5 opacity-30 cursor-not-allowed"
                                          : skill.enabled
                                            ? theme.toggleOn
                                            : "bg-white/10 cursor-pointer"
                                      }`}
                                    >
                                      {skill.categoryEnabled && (
                                        <motion.div
                                          layout
                                          transition={{
                                            type: "spring",
                                            stiffness: 500,
                                            damping: 28,
                                          }}
                                          className="w-3 h-3 rounded-full bg-white shadow-sm"
                                          style={{
                                            marginLeft: skill.enabled
                                              ? "auto"
                                              : "0px",
                                          }}
                                        />
                                      )}
                                    </button>
                                  </div>
                                );
                              })
                            ) : (
                              <span className="text-[9px] text-white/25 italic px-2">
                                Nenhuma rotina carregada.
                              </span>
                            )}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                ))}
              </nav>
            </div>

            {/* Footer */}
            <footer className="mt-6 pt-4 border-t border-white/5 flex items-center justify-between text-[9px] text-white/30 uppercase tracking-widest select-none">
              <span>Stark OS v2.0</span>
              <div className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                <span>Core Loaded</span>
              </div>
            </footer>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
}
