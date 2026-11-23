import { useEffect, useRef, useState } from "react";
import { api } from "../services/api.js";
import { runCommand } from "../services/consoleCommands.js";
import { useAuth } from "../auth.jsx";

// Very small Markdown: **bold**, `code`, *italic*, "- " bullets. Text is escaped by React.
function Inline({ text }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) return <b key={i}>{p.slice(2, -2)}</b>;
    if (p.startsWith("`") && p.endsWith("`")) return <code key={i}>{p.slice(1, -1)}</code>;
    if (p.startsWith("*") && p.endsWith("*") && p.length > 2) return <i key={i}>{p.slice(1, -1)}</i>;
    return <span key={i}>{p}</span>;
  });
}

function Answer({ text }) {
  return (
    <div className="ai-text">
      {text.split("\n").map((line, i) => {
        const bullet = line.match(/^(\s*)[-*] (.*)$/);
        if (bullet) return <div key={i} className="ai-bullet" style={{ paddingLeft: 10 + bullet[1].length * 8 }}>• <Inline text={bullet[2]} /></div>;
        return line.trim() ? <p key={i}><Inline text={line} /></p> : <div key={i} className="ai-gap" />;
      })}
    </div>
  );
}

const SUGGESTIONS = [
  "What is wrong right now?",
  "Which device is most at risk and why?",
  "Explain the latest alert",
  "Is the farm safe tonight?",
  "How does the satellite to 5G failover protect my devices?",
];

const WELCOME = {
  role: "assistant",
  content: "Hi, I'm the CyberShield AI security analyst. I read the live state of the twin (devices, alerts, routes, " +
    "failover, quarantine) and suggest what to do. I only advise: you decide whether to run a command.",
};
let saved = [WELCOME];

export default function AIAssistant({ alerts }) {
  const { can } = useAuth();
  const [messages, setMessages] = useState(saved);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(null);
  const endRef = useRef(null);

  useEffect(() => {
    api.aiStatus().then(setStatus).catch(() => {});
  }, []);
  useEffect(() => {
    saved = messages;
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages]);

  const add = (m) => setMessages((prev) => [...prev, m].slice(-60));

  async function ask(question, call) {
    if (!question.trim() || busy) return;
    add({ role: "user", content: question });
    setInput("");
    setBusy(true);
    try {
      const history = messages.filter((m) => m !== WELCOME).map(({ role, content }) => ({ role, content }));
      const res = await (call ? call() : api.aiChat(question, history));
      add({ role: "assistant", content: res.answer, source: res.source, commands: res.commands ?? [] });
    } catch (e) {
      add({ role: "assistant", content: `Error: ${e.message}`, source: "error", commands: [] });
    }
    setBusy(false);
  }

  async function runSuggested(cmd) {
    const { lines, tone } = await runCommand(cmd);
    add({ role: "tool", content: `$ ${cmd}\n${lines.join("\n")}`, tone });
  }

  const latest = alerts.find((a) => a.status === "open");

  return (
    <section className="panel ai-panel">
      <div className="panel-head">
        <h2>AI security assistant</h2>
        {status && (
          <span className={`small ${status.configured ? "tone-ok" : "muted"}`}>
            {status.configured ? `${status.provider_name || status.provider} · ${status.model}` : "offline analyst · add a DeepSeek API key in Admin → AI assistant"}
          </span>
        )}
      </div>
      <div className="ai-quick">
        <button className="btn btn-small" disabled={busy} onClick={() => ask("Incident report of this session", api.aiReport)}>Incident report</button>
        {latest && (
          <button className="btn btn-small" disabled={busy}
                  onClick={() => ask(`Explain alert #${latest.id} (${latest.alert_type.replace(/_/g, " ")})`, () => api.aiExplainAlert(latest.id))}>
            Explain latest alert #{latest.id}</button>
        )}
        {SUGGESTIONS.map((s) => (
          <button key={s} className="btn btn-small" disabled={busy} onClick={() => ask(s)}>{s}</button>
        ))}
      </div>
      <div className="ai-chat" role="log" aria-live="polite">
        {messages.map((m, i) => (
          <div key={i} className={`ai-msg ai-${m.role}`}>
            {m.role === "tool" ? (
              <pre className={`ai-tool console-${m.tone}`}>{m.content}</pre>
            ) : (
              <>
                <Answer text={m.content} />
                {m.source && m.source !== "error" && <div className="ai-source">answered by: {m.source === "offline" ? "built-in offline analyst" : m.source}</div>}
                {m.commands?.length > 0 && (
                  <div className="ai-commands">
                    {m.commands.map((c) => (
                      <button key={c} className="btn btn-small need-operator" onClick={() => runSuggested(c)} title="Run this console command">
                        ▶ {c}</button>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        ))}
        {busy && <div className="ai-msg ai-assistant muted">Thinking…</div>}
        <div ref={endRef} />
      </div>
      <form className="ai-input" onSubmit={(e) => { e.preventDefault(); ask(input); }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about the network, a device or an alert…"
               maxLength={2000} disabled={busy} aria-label="Question for the AI assistant" />
        <button className="btn btn-primary" disabled={busy || !input.trim()}>Ask</button>
      </form>
    </section>
  );
}
