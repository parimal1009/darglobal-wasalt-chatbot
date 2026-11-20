import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./App.css";

type Source = { title: string; url: string; source: string };
type Msg = { role: "user" | "assistant"; content: string; sources?: Source[]; error?: boolean };

const API = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

const SUGGESTIONS = [
  "What is Dar Global and what does it do?",
  "Which DarGlobal projects are in Dubai or Oman?",
  "What services does Wasalt offer?",
  "Show me property listings on Wasalt in Riyadh",
];

export default function App() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    const history = messages.map(({ role, content }) => ({ role, content }));
    setMessages((m) => [...m, { role: "user", content: q }, { role: "assistant", content: "" }]);
    setInput("");
    setBusy(true);
    const patch = (fn: (m: Msg) => Msg) =>
      setMessages((all) => all.map((m, i) => (i === all.length - 1 ? fn(m) : m)));
    try {
      const res = await fetch(`${API}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: q, history }),
      });
      if (!res.ok || !res.body) throw new Error(`Server error ${res.status}`);
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";
        for (const p of parts) {
          if (!p.startsWith("data: ")) continue;
          const ev = JSON.parse(p.slice(6));
          if (ev.type === "sources") patch((m) => ({ ...m, sources: ev.sources }));
          else if (ev.type === "token") patch((m) => ({ ...m, content: m.content + ev.text }));
          else if (ev.type === "error") patch((m) => ({ ...m, content: m.content || `Sorry, the model failed: ${ev.message}`, error: true }));
        }
      }
    } catch (e) {
      patch((m) => ({ ...m, content: `Sorry, something went wrong: ${(e as Error).message}`, error: true }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <header>
        <h1>DarGlobal &amp; Wasalt Assistant</h1>
        <p>Ask about Dar Global projects and Wasalt real-estate services, answered from scraped public data.</p>
      </header>
      <main>
        {messages.length === 0 && (
          <div className="suggestions">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => send(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}${m.error ? " error" : ""}`}>
            <div className="bubble">
              {m.content ? (
                m.role === "assistant" ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                ) : (
                  m.content
                )
              ) : busy && i === messages.length - 1 ? (
                "Thinking…"
              ) : (
                ""
              )}
            </div>
            {m.sources && m.sources.length > 0 && m.content && (
              <div className="sources">
                {m.sources.map((s) => (
                  <a key={s.url} href={s.url} target="_blank" rel="noreferrer" title={s.title}>
                    {s.source === "wasalt" ? "Wasalt" : "DarGlobal"}: {s.title.slice(0, 40)}
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={endRef} />
      </main>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask a question…" disabled={busy} />
        <button type="submit" disabled={busy || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
