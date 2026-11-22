"use client";
import { useEffect, useRef, useState } from "react";
import { api, type Answer, type TraceEvent } from "@/lib/api";
import { inr, fmtDate } from "@/lib/fmt";


export type Msg = { role: "user" | "assistant"; content: string; viewerId: string; viewerName: string; answer?: Answer; error?: boolean };
export type Chat = { msgs: Msg[]; busy: boolean; live: TraceEvent[]; startedAt?: number };
export const emptyChat = (): Chat => ({ msgs: [], busy: false, live: [] });

type Props = {
  familyId: string; memberId: string; memberName: string; suggested: string[];
  chat: Chat; update: (familyId: string, fn: (c: Chat) => Chat) => void; onAnswered?: (familyId: string) => void;
};

export default function AskPanel({ familyId, memberId, memberName, suggested, chat, update, onAnswered }: Props) {
  const { msgs, busy, live } = chat;
  const [input, setInput] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const end = useRef<HTMLDivElement>(null);
  const lastAnswer = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const last = msgs[msgs.length - 1];
    if (last?.role === "assistant") lastAnswer.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    else end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [msgs, busy, live.length]);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) send(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!busy) return;
    const t0 = chat.startedAt ?? Date.now();
    setElapsed((Date.now() - t0) / 1000);
    const t = setInterval(() => setElapsed((Date.now() - t0) / 1000), 100);
    return () => clearInterval(t);
  }, [busy, chat.startedAt]);

  async function send(q: string) {
    if (!q.trim() || busy) return;
    // Capture the family and viewer now: the answer must land in this family's thread even if the user switches away.
    const fid = familyId, viewerId = memberId, viewerName = memberName;
    // Privacy: only this viewer's own earlier turns go to the agent as history, never another member's answers.
    const history = msgs.filter((m) => m.viewerId === viewerId && !m.error).map((m) => ({ role: m.role, content: m.content }));
    update(fid, (c) => ({ ...c, msgs: [...c.msgs, { role: "user", content: q, viewerId, viewerName }], busy: true, live: [], startedAt: Date.now() }));
    setInput("");
    try {
      const a = await api.askStream(q, viewerId, history, (t) => update(fid, (c) => ({ ...c, live: [...c.live, t] })), fid);
      update(fid, (c) => ({ ...c, msgs: [...c.msgs, { role: "assistant", content: a.answer, answer: a, viewerId, viewerName }] }));
      onAnswered?.(fid);
    } catch (e) {
      update(fid, (c) => ({ ...c, msgs: [...c.msgs, { role: "assistant", content: String(e), error: true, viewerId, viewerName }] }));
    } finally {
      update(fid, (c) => ({ ...c, busy: false, live: [], startedAt: undefined }));
    }
  }

  return (
    <div className="card flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-line px-5 py-3">
        <div>
          <h2 className="text-sm font-semibold tracking-wide">Ask FamilyOS</h2>
          <p className="text-[11px] text-muted">Answers grounded in your family&apos;s records · asking as <span className="text-accent">{memberName}</span></p>
        </div>
        {msgs.length > 0 && !busy && <button onClick={() => update(familyId, () => emptyChat())} className="text-[11px] text-muted hover:text-ink">Clear</button>}
      </div>

      <div className="scroll-thin flex-1 space-y-4 overflow-y-auto px-5 py-4">
        {msgs.length === 0 && (
          <div className="py-6 text-center">
            <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-accent/15 text-accent">✦</div>
            <p className="text-sm text-muted">Ask about decisions that involve the whole family.</p>
          </div>
        )}
        {msgs.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="fade-up flex flex-col items-end gap-0.5">
              <span className="text-[10px] text-muted">asked as {m.viewerName}</span>
              <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-sky/15 px-4 py-2 text-sm">{m.content}</div>
            </div>
          ) : m.error ? (
            <div key={i} className="rounded-xl border border-rose/40 bg-rose/10 p-3 text-xs text-rose">{m.content}</div>
          ) : (
            <div key={i} ref={i === msgs.length - 1 ? lastAnswer : undefined} className="scroll-mt-2">
              <AnswerCard a={m.answer!} />
            </div>
          )
        )}
        {busy && <LiveTrace events={live} elapsed={elapsed} />}
        <div ref={end} />
      </div>

      <div className="border-t border-line p-3">
        <div className="mb-2 flex flex-wrap gap-1.5">
          {suggested.map((s) => (
            <button key={s} onClick={() => send(s)} disabled={busy}
              className="rounded-full border border-line px-2.5 py-1 text-[11px] text-muted transition hover:border-accent/60 hover:text-ink disabled:opacity-40">
              {s}
            </button>
          ))}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="flex gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask a question about your family's finances…"
            className="flex-1 rounded-xl border border-line bg-bg/60 px-4 py-2.5 text-sm outline-none placeholder:text-muted/70 focus:border-accent/60" />
          <button disabled={busy || !input.trim()} className="rounded-xl bg-accent px-4 text-sm font-semibold text-bg transition hover:brightness-110 disabled:opacity-40">
            Ask
          </button>
        </form>
      </div>
    </div>
  );
}

const KIND: Record<string, { icon: string; cls: string }> = {
  llm: { icon: "✦", cls: "text-violet" },
  tool: { icon: "⚙", cls: "text-sky" },
  verify: { icon: "✔", cls: "text-accent" },
  step: { icon: "•", cls: "text-muted" },
};

function LiveTrace({ events, elapsed }: { events: TraceEvent[]; elapsed: number }) {
  const thinking = events.length === 0 || events[events.length - 1].kind !== "llm";
  return (
    <div className="fade-up rounded-xl border border-violet/30 bg-violet/5 p-3">
      <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-wider">
        <span className="font-semibold text-violet">Claude is investigating your family&apos;s finances</span>
        <span className="font-mono text-muted">{elapsed.toFixed(1)}s</span>
      </div>
      <ol className="space-y-1">
        {events.map((t, i) => {
          const k = KIND[t.kind ?? "step"] ?? KIND.step;
          return (
            <li key={i} className="fade-up flex gap-2 text-[11px] leading-snug">
              <span className={`w-3 shrink-0 ${k.cls}`}>{k.icon}</span>
              <span className={`shrink-0 font-medium ${t.kind === "tool" ? "font-mono text-sky" : ""}`}>{t.node.replace("tool · ", "")}</span>
              {/graph/.test(t.node) && <span className="shrink-0 rounded bg-sky/15 px-1 text-[9px] font-semibold text-sky">NEO4J</span>}
              <span className="min-w-0 truncate text-muted">{t.detail}</span>
            </li>
          );
        })}
        <li className="flex items-center gap-2 text-[11px] text-muted">
          <span className="pulse inline-block h-2 w-2 rounded-full bg-violet" />
          {thinking ? "Claude is reasoning…" : "Running tools…"}
        </li>
      </ol>
    </div>
  );
}

function AnswerCard({ a }: { a: Answer }) {
  const [tab, setTab] = useState<"calc" | "evidence" | "assume" | "trace" | null>(null);
  const conf = { high: "text-accent bg-accent/15", medium: "text-gold bg-gold/15", low: "text-rose bg-rose/15" }[a.confidence];
  return (
    <div className="fade-up space-y-3 rounded-2xl rounded-bl-sm border border-line bg-panel2/70 p-4">
      <div className="flex flex-wrap items-center gap-2 text-[10px]">
        <span className={`rounded-full px-2 py-0.5 font-semibold uppercase tracking-wide ${conf}`}>{a.confidence} confidence</span>
        {a.mode === "agentic" ? (
          <>
            <span className="rounded-full bg-violet/15 px-2 py-0.5 text-violet">✦ Claude agent · {String(a.plan.tool_calls)} tool calls</span>
            <span className="rounded-full bg-accent/10 px-2 py-0.5 text-accent">
              every number verified{a.verification.self_corrections ? ` · self-corrected ${a.verification.self_corrections}×` : ""}
            </span>
          </>
        ) : (
          <span className="rounded-full bg-gold/15 px-2 py-0.5 text-gold">
            {a.mode === "deterministic_fallback" ? "LLM unavailable · deterministic fallback" : "deterministic mode"}
          </span>
        )}
        {!!a.live_sources?.length && (
          <span className="rounded-full bg-sky/15 px-2 py-0.5 text-sky">◉ Live MF Engine data</span>
        )}
        {a.withheld_record_count > 0 && (
          <span className="rounded-full bg-violet/15 px-2 py-0.5 text-violet">🔒 {a.withheld_record_count} private record{a.withheld_record_count > 1 ? "s" : ""} withheld</span>
        )}
      </div>
      <p className="text-[15px] leading-relaxed">{a.answer}</p>

      <div className="grid gap-2 sm:grid-cols-2">
        {a.key_findings.map((f, i) => (
          <div key={i} className="rounded-lg border border-line bg-bg/40 px-3 py-2 text-xs leading-snug">
            <span className="mr-1 text-accent">✔</span>{f}
          </div>
        ))}
      </div>

      {a.context_insights.length > 0 && (
        <div className="rounded-xl border border-sky/25 bg-sky/5 p-3">
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-sky">Family context · cross-member reasoning</div>
          <ul className="space-y-1 text-xs text-ink/90">
            {a.context_insights.map((c, i) => <li key={i} className="flex gap-2"><span className="text-sky">↳</span>{c}</li>)}
          </ul>
        </div>
      )}

      <div className="flex gap-1 border-b border-line text-[11px]">
        {([["calc", `Calculations (${a.calculations.length})`], ["evidence", `Evidence (${a.supporting_records.length + (a.live_sources?.length ?? 0)})`], ["assume", `Assumptions & gaps`], ["trace", a.mode === "agentic" ? "Agent trace" : "Pipeline trace"]] as const).map(([k, l]) => (
          <button key={k} onClick={() => setTab(tab === k ? null : k)}
            className={`-mb-px border-b-2 px-2.5 py-1.5 transition ${tab === k ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"}`}>{l}</button>
        ))}
      </div>

      {tab === "calc" && (
        <table className="w-full text-[11px]">
          <tbody>
            {a.calculations.map((c, i) => (
              <tr key={i} className="border-b border-line/50 last:border-0 align-top">
                <td className="py-1.5 pr-2 text-ink/90">{c.label}</td>
                <td className="py-1.5 pr-2 font-mono text-[10px] text-muted">{c.formula}</td>
                <td className="py-1.5 text-right font-mono font-semibold text-accent whitespace-nowrap">{c.result}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {tab === "evidence" && (
        <div className="space-y-1.5">
          {a.live_sources?.map((l, i) => (
            <div key={`live-${i}`} className="flex items-center justify-between gap-3 rounded-lg border border-sky/25 bg-sky/5 px-3 py-2 text-[11px]">
              <div className="min-w-0 truncate"><span className="font-semibold text-sky">MF Engine · live</span> · <span className="font-mono">{l.tool}</span>
                {Object.keys(l.args).length ? <span className="text-muted"> ({Object.entries(l.args).map(([k, v]) => `${k}=${v}`).join(", ")})</span> : null}</div>
              <div className="whitespace-nowrap font-mono text-muted">{l.ms} ms</div>
            </div>
          ))}
          {a.supporting_records.map((r) => (
            <div key={r.record_id} className="flex items-center justify-between gap-3 rounded-lg bg-bg/40 px-3 py-2 text-[11px]">
              <div className="min-w-0">
                <div className="truncate"><span className="font-mono text-muted">{r.record_id}</span> · {r.member.split(" ")[0]} · {r.description}</div>
                <div className="truncate text-[10px] text-muted">📄 {r.source.filename} · from {fmtDate(r.valid_from)} · confidence {Math.round(r.confidence * 100)}%</div>
              </div>
              <div className="whitespace-nowrap font-mono font-semibold">{inr(r.amount)}{r.frequency === "monthly" ? "/mo" : ""}</div>
            </div>
          ))}
        </div>
      )}
      {tab === "assume" && (
        <div className="space-y-2 text-[11px]">
          <ul className="space-y-1">{a.assumptions.map((x, i) => <li key={i} className="text-ink/85">◦ {x}</li>)}</ul>
          {a.missing_information.length > 0 && (
            <div className="rounded-lg border border-gold/30 bg-gold/5 p-2">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-gold">Missing information — not assumed</div>
              <ul className="space-y-0.5">{a.missing_information.map((x, i) => <li key={i}>⚠ {x}</li>)}</ul>
            </div>
          )}
          <p className="text-[10px] text-muted">Estimates for planning only — not a lending or investment recommendation.</p>
        </div>
      )}
      {tab === "trace" && (
        <div className="space-y-1">
          {a.trace.map((t, i) => {
            const k = KIND[t.kind ?? "step"] ?? KIND.step;
            return (
              <div key={i} className="flex gap-2 text-[11px]">
                <span className={`w-4 text-center ${k.cls}`}>{k.icon}</span>
                <span className={`w-44 shrink-0 font-semibold ${t.kind === "tool" ? "font-mono text-sky" : ""}`}>{t.node}</span>
                <span className="min-w-0 flex-1 break-words text-muted">{t.detail}</span>
                <span className="font-mono text-[10px] text-muted">{t.ms}ms</span>
              </div>
            );
          })}
          <div className="pt-1 text-[10px] text-muted">
            Checks: {a.verification.checks.map((c) => `${c.ok ? "✔" : "✘"} ${c.check}`).join(" · ")}
          </div>
        </div>
      )}
    </div>
  );
}
