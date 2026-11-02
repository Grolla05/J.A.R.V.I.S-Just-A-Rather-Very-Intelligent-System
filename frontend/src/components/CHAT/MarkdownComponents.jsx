export const MD_COMPONENTS = {
  p: ({ children }) => (
    <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-white">{children}</strong>
  ),
  em: ({ children }) => <em className="italic text-white/75">{children}</em>,
  h1: ({ children }) => (
    <h1 className="text-sm font-bold text-white mt-3 mb-1.5 first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-xs font-bold text-white/90 mt-2.5 mb-1 first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-xs font-semibold text-white/80 mt-2 mb-1 first:mt-0">{children}</h3>
  ),
  ul: ({ children }) => (
    <ul className="list-none mb-2 space-y-0.5 pl-3">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-none mb-2 space-y-0.5 pl-3 [counter-reset:item]">{children}</ol>
  ),
  li: ({ children, ordered }) => (
    <li className="flex gap-1.5 items-start text-white/82">
      <span className="mt-px shrink-0 opacity-50" style={{ fontSize: "9px" }}>
        {ordered ? "›" : "▸"}
      </span>
      <span>{children}</span>
    </li>
  ),
  code: ({ inline, children }) => {
    if (inline)
      return (
        <code
          className="px-1.5 py-0.5 rounded-md text-[10px] font-mono"
          style={{
            background: "rgba(34,211,238,0.1)",
            border: "1px solid rgba(34,211,238,0.18)",
            color: "rgba(34,211,238,0.9)",
          }}
        >
          {children}
        </code>
      );
    return (
      <code className="block w-full text-[10px] font-mono leading-relaxed" style={{ color: "rgba(200,220,255,0.88)" }}>
        {children}
      </code>
    );
  },
  pre: ({ children }) => (
    <pre
      className="rounded-xl p-3 my-2 overflow-x-auto text-[10px] font-mono"
      style={{
        background: "rgba(6,10,22,0.75)",
        border: "1px solid rgba(255,255,255,0.07)",
        boxShadow: "0 4px 12px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.04)",
      }}
    >
      {children}
    </pre>
  ),
  blockquote: ({ children }) => (
    <blockquote
      className="pl-3 my-1.5 text-white/60 italic"
      style={{ borderLeft: "2px solid rgba(34,211,238,0.4)" }}
    >
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-2 border-white/8" />,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="underline underline-offset-2 text-cyan-400/80 hover:text-cyan-300 transition-colors"
    >
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto my-2">
      <table className="w-full text-[10px] border-collapse">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th
      className="px-2 py-1 text-left font-semibold text-white/70"
      style={{ borderBottom: "1px solid rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.03)" }}
    >
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td
      className="px-2 py-1 text-white/70"
      style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}
    >
      {children}
    </td>
  ),
};
