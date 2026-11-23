// Small Markdown for AI answers and reports: # headings, **bold**, `code`, *italic*, [text](url), "- " bullets,
// and evidence citations [E3] (clickable when onCite is given). Text is escaped by React.
function Inline({ text, onCite }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[E\d+\]|\[[^\]]+\]\(https?:\/\/[^)\s]+\)|\*[^*\s][^*]*\*)/g);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) return <b key={i}>{p.slice(2, -2)}</b>;
    if (p.startsWith("`") && p.endsWith("`")) return <code key={i}>{p.slice(1, -1)}</code>;
    const cite = p.match(/^\[(E\d+)\]$/);
    if (cite) return <button key={i} type="button" className="cite" onClick={() => onCite?.(cite[1])} title="Show this evidence">{cite[1]}</button>;
    const link = p.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/);
    if (link) return <a key={i} href={link[2]} target="_blank" rel="noreferrer">{link[1]}</a>;
    if (p.startsWith("*") && p.endsWith("*") && p.length > 2) return <i key={i}>{p.slice(1, -1)}</i>;
    return <span key={i}>{p}</span>;
  });
}

export default function Markdown({ text, onCite }) {
  return (
    <div className="ai-text">
      {text.split("\n").map((line, i) => {
        const h = line.match(/^(#{1,3}) (.*)$/);
        if (h) { const H = `h${Math.min(h[1].length + 1, 4)}`; return <H key={i} className="md-h"><Inline text={h[2]} onCite={onCite} /></H>; }
        if (line.startsWith("> ")) return <blockquote key={i} className="md-quote"><Inline text={line.slice(2)} onCite={onCite} /></blockquote>;
        const bullet = line.match(/^(\s*)[-*] (.*)$/);
        if (bullet) return <div key={i} className="ai-bullet" style={{ paddingLeft: 10 + bullet[1].length * 8 }}>• <Inline text={bullet[2]} onCite={onCite} /></div>;
        return line.trim() ? <p key={i}><Inline text={line} onCite={onCite} /></p> : <div key={i} className="ai-gap" />;
      })}
    </div>
  );
}
