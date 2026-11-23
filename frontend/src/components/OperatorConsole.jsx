import { useEffect, useRef, useState } from "react";
import { COMMAND_NAMES, runCommand } from "../services/consoleCommands.js";
import { useAuth } from "../auth.jsx";

// Terminal-style console for the network security operator.
// Output and history live at module level, so they survive a tab switch.
const WELCOME = [
  { kind: "out", tone: "muted", text: "CyberShield operator console. Type help to see all commands." },
  { kind: "out", tone: "muted", text: "Every command acts on the simulation only. Nothing leaves this computer." },
];
let savedLines = WELCOME;
let savedHistory = [];

export default function OperatorConsole() {
  const { user } = useAuth();
  const prompt = `${user?.username ?? "operator"}@cybershield:~$`;
  const [lines, setLines] = useState(savedLines);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const historyIndex = useRef(-1);
  const screenRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    savedLines = lines;
    const el = screenRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  useEffect(() => inputRef.current?.focus(), []);

  function submit(e) {
    e.preventDefault();
    execute(input);
  }

  async function execute(raw) {
    const command = raw.trim();
    setInput("");
    historyIndex.current = -1;
    if (!command) return;
    if (savedHistory[savedHistory.length - 1] !== command) savedHistory = [...savedHistory, command].slice(-100);
    if (command.toLowerCase() === "clear") {
      setLines([]);
      return;
    }
    setLines((prev) => [...prev, { kind: "cmd", text: command }]);
    setBusy(true);
    const { lines: out, tone } = await runCommand(command);
    setBusy(false);
    setLines((prev) => [...prev, ...out.map((text) => ({ kind: "out", tone, text }))].slice(-1000));
    inputRef.current?.focus();
  }

  function onKeyDown(e) {
    if (e.key === "ArrowUp" || e.key === "ArrowDown") {
      if (!savedHistory.length) return;
      e.preventDefault();
      let i = historyIndex.current;
      if (e.key === "ArrowUp") i = i === -1 ? savedHistory.length - 1 : Math.max(0, i - 1);
      else i = i === -1 ? -1 : i + 1 >= savedHistory.length ? -1 : i + 1;
      historyIndex.current = i;
      setInput(i === -1 ? "" : savedHistory[i]);
    } else if (e.key === "Tab") {
      e.preventDefault();
      const [word, ...rest] = input.split(" ");
      if (rest.length) return;
      const matches = COMMAND_NAMES.filter((c) => c.startsWith(word.toLowerCase()));
      if (matches.length === 1) setInput(`${matches[0]} `);
      else if (matches.length > 1) {
        setLines((prev) => [...prev, { kind: "out", tone: "muted", text: matches.join("   ") }]);
      }
    } else if (e.key === "l" && e.ctrlKey) {
      e.preventDefault();
      setLines([]);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Operator console</h2>
      </div>
      <div className="console" onClick={() => inputRef.current?.focus()}>
        <div className="console-screen" ref={screenRef} role="log" aria-live="polite">
          {lines.map((l, i) =>
            l.kind === "cmd" ? (
              <div key={i} className="console-line console-cmd"><span className="console-prompt">{prompt}</span> {l.text}</div>
            ) : (
              <div key={i} className={`console-line console-${l.tone}`}>{l.text || " "}</div>
            ),
          )}
          {busy && <div className="console-line console-muted">…</div>}
        </div>
        <form className="console-input" onSubmit={submit}>
          <span className="console-prompt">{prompt}</span>
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={busy}
            spellCheck={false}
            autoComplete="off"
            autoCapitalize="off"
            aria-label="Console command"
          />
        </form>
      </div>
      <div className="console-quick">
        {["help", "status", "devices", "routes", "alerts", "events"].map((c) => (
          <button key={c} className="btn btn-small" disabled={busy}
                  onClick={() => execute(c)}>
            {c}
          </button>
        ))}
      </div>
    </section>
  );
}
