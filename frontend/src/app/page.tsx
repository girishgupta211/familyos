"use client";
import { useCallback, useEffect, useState } from "react";
import AskPanel, { emptyChat, type Chat } from "@/components/AskPanel";
import ContextGraph from "@/components/ContextGraph";
import { api, setFamily, type FamilyInfo, type ContextB, type Health, type GNode, type Graph, type Overview, type TimelineEvent } from "@/lib/api";
import { first, fmtDate, inr, inrShort } from "@/lib/fmt";

const NEW_PAYSLIP = {
  record_id: "R101", member_id: "M001", type: "income", category: "salary",
  description: "Monthly salary — Orbit Systems (new employer)", amount: "300000", currency: "INR", frequency: "monthly",
  entity: { entity_id: "EMP-ORBIT", entity_type: "employer", name: "Orbit Systems Ltd" },
  source: { document_id: "D101", filename: "rajesh_orbit_offer_and_payslip.pdf", document_type: "payslip" },
  valid_from: "2026-11-01", valid_until: null, confidence: 0.97,
};

const CHAT_KEY = "familyos.chats.v1";

const ROLE_ICON: Record<string, string> = { father: "👨", mother: "👩", son: "🧑", daughter: "👧" };

export default function Home() {
  const [families, setFamilies] = useState<FamilyInfo[]>([]);
  const [familyId, setFamilyId] = useState("F001");
  const [viewer, setViewer] = useState("M003");
  const [ov, setOv] = useState<Overview | null>(null);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [ctx, setCtx] = useState<ContextB | null>(null);
  const [llm, setLlm] = useState<Health | null>(null);
  const [tab, setTab] = useState<"graph" | "members" | "timeline">("graph");
  const [picked, setPicked] = useState<GNode | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [err, setErr] = useState<string | null>(null);
  // One conversation per family, kept across family switches and page reloads (browser-only convenience).
  const [chats, setChats] = useState<Record<string, Chat>>({});
  const [chatsLoaded, setChatsLoaded] = useState(false);
  useEffect(() => {
    try {
      const raw = localStorage.getItem(CHAT_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as Record<string, Chat["msgs"]>;
        setChats(Object.fromEntries(Object.entries(saved).map(([k, msgs]) => [k, { ...emptyChat(), msgs }])));
      }
    } catch { /* storage unavailable: start empty */ }
    setChatsLoaded(true);
  }, []);
  useEffect(() => {
    if (!chatsLoaded) return;
    try {
      localStorage.setItem(CHAT_KEY, JSON.stringify(Object.fromEntries(Object.entries(chats).map(([k, c]) => [k, c.msgs]))));
    } catch { /* quota or blocked storage: keep in memory only */ }
  }, [chats, chatsLoaded]);
  const updateChat = useCallback((fid: string, fn: (c: Chat) => Chat) => {
    setChats((all) => ({ ...all, [fid]: fn(all[fid] ?? emptyChat()) }));
  }, []);

  useEffect(() => {
    api.families().then((fs) => {
      setFamilies(fs);
      const want = new URLSearchParams(window.location.search).get("family");
      const f = fs.find((x) => x.family_id === want);
      if (f) {
        setFamily(f.family_id);
        setFamilyId(f.family_id);
        if (f.default_member_id) setViewer(f.default_member_id);
      }
    }).catch(() => {});
  }, []);

  function switchFamily(fid: string) {
    const f = families.find((x) => x.family_id === fid);
    setFamily(fid);
    setPicked(null);
    setFresh(new Set());
    setOv(null); setGraph(null); setCtx(null);
    setFamilyId(fid);
    if (f?.default_member_id) setViewer(f.default_member_id);
  }

  const load = useCallback(async () => {
    try {
      const [o, g, c] = await Promise.all([api.overview(viewer), api.graph(viewer), api.context(viewer)]);
      setOv(o); setGraph(g); setCtx(c); setErr(null);
    } catch (e) {
      setErr(String(e));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewer, familyId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.health().then(setLlm).catch(() => { /* keep last known status */ }); }, [ov]);

  const members = ov?.members ?? [];
  const viewerName = members.find((m) => m.member_id === viewer)?.name ?? viewer;
  const s = ov?.summary;

  async function simulate() {
    const r = await api.ingest([NEW_PAYSLIP]);
    setFresh(new Set(r.memory_changes.map((e) => e.record_id)));
    setTab("timeline");
    await load();
  }
  async function reset() {
    await api.reset();
    setFresh(new Set());
    await load();
  }

  return (
    <main className="mx-auto max-w-[1440px] px-4 py-5 sm:px-6">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-accent to-sky text-lg font-black text-bg">F</div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">FamilyOS</h1>
            <p className="text-xs text-muted">Your family&apos;s financial life. Understood by AI.</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <label htmlFor="family" className="sr-only">Family</label>
          <select id="family" value={familyId} onChange={(e) => switchFamily(e.target.value)}
            className="rounded-full border border-line bg-panel px-3 py-1.5 text-xs text-ink outline-none focus:border-accent/60">
            {families.map((f) => (
              <option key={f.family_id} value={f.family_id}>
                {f.name}{f.city ? ` · ${f.city}` : ""} ({f.member_count ?? "?"}){chats[f.family_id]?.busy ? " · answering…" : chats[f.family_id]?.msgs.length ? ` · ${chats[f.family_id].msgs.filter((m) => m.role === "user").length} asked` : ""}
              </option>
            ))}
          </select>
          <span className={`rounded-full px-2.5 py-1 ${llm === null ? "bg-line text-muted" : llm.llm ? "bg-accent/15 text-accent" : "bg-gold/15 text-gold"}`}>
            {llm === null ? "Checking AI…" : llm.llm ? `✦ Agentic · ${llm.model}${llm.speed === "fast" ? " · fast" : ""}` : "● Fallback mode (Claude unavailable)"}
          </span>
          {llm?.neo4j && (
            <span className={`rounded-full px-2.5 py-1 ${llm.neo4j.connected ? "bg-sky/15 text-sky" : "bg-line text-muted"}`}>
              {llm.neo4j.connected ? `◆ Neo4j · ${llm.neo4j.nodes} nodes` : "◇ Neo4j offline · in-memory graph"}
            </span>
          )}
          <div className="flex items-center gap-1 rounded-full border border-line bg-panel p-1">
            <span className="px-2 text-muted">Viewing as</span>
            {members.map((m) => (
              <button key={m.member_id} onClick={() => setViewer(m.member_id)}
                className={`rounded-full px-3 py-1 transition ${viewer === m.member_id ? "bg-accent text-bg font-semibold" : "text-muted hover:text-ink"}`}>
                {first(m.name)}
              </button>
            ))}
          </div>
        </div>
      </header>

      {families.find((f) => f.family_id === familyId)?.summary && (
        <p className="-mt-2 mb-4 text-xs text-muted">{families.find((f) => f.family_id === familyId)?.summary}</p>
      )}

      {err && <div className="mb-4 rounded-xl border border-rose/40 bg-rose/10 p-3 text-sm text-rose">Backend unreachable: {err}</div>}

      {/* Family overview */}
      <section className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi label="Family income" value={inrShort(s?.monthly_income)} sub="per month · all earners" tone="accent" />
        <Kpi label="Monthly cash flow" value={inrShort(s?.monthly_surplus)} sub={`after ${inrShort(s?.monthly_expenses)} spend + ${inrShort(s?.monthly_emi)} EMI`} tone="sky" />
        <Kpi label="Investments" value={inrShort(s?.investments)} sub={`+ ${inrShort(s?.bank_balances)} in bank`} tone="violet" />
        <Kpi label="Total assets" value={inrShort(s?.total_assets)} sub={`${inrShort(s?.property_assets)} property & gold · ${inrShort(s?.locked_investments)} locked`} tone="gold" />
        <Kpi label="Liabilities" value={inrShort(s?.total_liabilities)} sub="loans & cards outstanding" tone="rose" />
        <Kpi label="Net worth" value={inrShort(s?.net_worth)} sub={ov?.withheld_record_count ? `🔒 ${ov.withheld_record_count} private record${ov.withheld_record_count > 1 ? "s" : ""} excluded` : "complete view"} tone="accent" />
      </section>

      {ov && ov.goals.length > 0 && (
        <div className="fade-up mb-4 flex flex-wrap items-center gap-2 text-xs">
          <span className="text-muted">Remembered family goals:</span>
          {ov.goals.map((g) => (
            <span key={g.kind} className="rounded-full border border-gold/40 bg-gold/10 px-3 py-1 text-gold">
              🎯 {g.label} · by {fmtDate(g.target_date)}
            </span>
          ))}
        </div>
      )}

      <section className="grid gap-5 lg:grid-cols-12">
        <div className="lg:col-span-7 h-[calc(100vh-230px)] min-h-[620px]">
          <AskPanel familyId={familyId} memberId={viewer} memberName={first(viewerName)}
            chat={chats[familyId] ?? emptyChat()} update={updateChat}
            onAnswered={(fid) => { if (fid === familyId) load(); }}
            suggested={families.find((f) => f.family_id === familyId)?.questions ?? []} />
        </div>

        <div className="card flex flex-col lg:col-span-5 lg:h-[calc(100vh-230px)] lg:min-h-[620px]">
          <div className="flex items-center justify-between border-b border-line px-4">
            <div className="flex gap-1 text-xs">
              {([["graph", "Family context graph"], ["members", "Members"], ["timeline", "Memory timeline"]] as const).map(([k, l]) => (
                <button key={k} onClick={() => setTab(k)}
                  className={`-mb-px border-b-2 px-3 py-3 transition ${tab === k ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"}`}>{l}</button>
              ))}
            </div>
          </div>
          <div className="scroll-thin flex-1 overflow-y-auto p-4">
            {tab === "graph" && graph && (
              <>
                <ContextGraph graph={graph} onSelect={setPicked} />
                {picked && picked.kind !== "family" && ctx && <NodeDetail node={picked} ctx={ctx} />}
                {!picked && <p className="mt-2 text-[11px] text-muted">Hover or click any node to trace who owns, earns, owes or is covered by what.</p>}
                {llm?.neo4j?.connected && (
                  <p className="mt-2 rounded-lg border border-sky/25 bg-sky/5 px-3 py-2 text-[11px] text-muted">
                    <span className="font-semibold text-sky">◆ Mirrored in Neo4j</span> · {llm.neo4j.nodes} nodes, {llm.neo4j.relationships} relationships
                    {llm.neo4j.private_records_excluded ? ` · ${llm.neo4j.private_records_excluded} private record${llm.neo4j.private_records_excluded > 1 ? "s" : ""} kept out of the shared graph` : ""}
                    {" · "}<a href="http://localhost:7474" target="_blank" rel="noreferrer" className="text-sky underline">Open Neo4j Browser</a>
                  </p>
                )}
              </>
            )}
            {tab === "members" && ov && (
              <div className="space-y-3">
                {ov.members.map((m) => (
                  <div key={m.member_id} className="rounded-xl border border-line bg-bg/40 p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-xl">{ROLE_ICON[m.relationship] ?? "🙂"}</span>
                        <div>
                          <div className="text-sm font-semibold">{m.name}</div>
                          <div className="text-[11px] capitalize text-muted">{m.relationship} · {m.member_id}</div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="font-mono text-sm text-accent">{inr(m.monthly_income)}</div>
                        <div className="text-[10px] text-muted">monthly income</div>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-1.5">
                      {m.holdings.filter((h) => h.type !== "tax").map((h) => (
                        <div key={h.record_id} className="rounded-md bg-panel2 px-2 py-1.5 text-[11px]">
                          <div className="truncate text-muted">{h.label}</div>
                          <div className={`font-mono ${h.type === "loan" || h.type === "expense" ? "text-rose" : "text-ink"}`}>
                            {inrShort(h.amount)}{h.frequency === "monthly" ? "/mo" : ""}{h.emi ? ` · EMI ${inrShort(h.emi)}` : ""}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
            {tab === "timeline" && ctx && (
              <div>
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <button onClick={simulate} disabled={familyId !== "F001"} title={familyId !== "F001" ? "Demo document is for the Mehta family" : undefined} className="disabled:opacity-40 rounded-lg bg-sky/15 px-3 py-1.5 text-xs text-sky hover:bg-sky/25">
                    ⇪ Simulate new document from Financial Data Engine
                  </button>
                  <button onClick={reset} className="rounded-lg px-2 py-1.5 text-xs text-muted hover:text-ink">Reset demo</button>
                </div>
                <Timeline events={ctx.memory_timeline} members={ctx.members} fresh={fresh} />
              </div>
            )}
          </div>
        </div>
      </section>

      <footer className="mt-6 text-center text-[11px] text-muted">
        Synthetic demo family · Financial Data Engine → Contract A → Context Engine → LangGraph agent (Claude + deterministic finance tools) · every number verified · not financial advice
      </footer>
    </main>
  );
}

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub: string; tone: string }) {
  const color = { accent: "text-accent", sky: "text-sky", violet: "text-violet", gold: "text-gold", rose: "text-rose" }[tone];
  return (
    <div className="card px-4 py-3">
      <div className="text-[11px] uppercase tracking-wider text-muted">{label}</div>
      <div className={`mt-1 font-mono text-2xl font-semibold ${color}`}>{value}</div>
      <div className="mt-0.5 truncate text-[11px] text-muted">{sub}</div>
    </div>
  );
}

function NodeDetail({ node, ctx }: { node: GNode; ctx: ContextB }) {
  const recs = node.kind === "member"
    ? ctx.financial_context.filter((f) => f.member_id === node.id && f.status === "current" && f.type !== "transaction")
    : ctx.financial_context.filter((f) => node.record_ids?.includes(f.record_id));
  return (
    <div className="fade-up mt-3 rounded-xl border border-line bg-bg/40 p-3">
      <div className="mb-2 text-sm font-semibold">{node.label}</div>
      <div className="space-y-1">
        {recs.map((r) => (
          <div key={r.record_id} className="flex justify-between gap-2 text-[11px]">
            <span className={`truncate ${r.status === "superseded" ? "text-muted line-through" : ""}`}>
              <span className="font-mono text-muted">{r.record_id}</span> {r.description} · {fmtDate(r.valid_from)}
              <span className="ml-1 rounded bg-line px-1 text-[9px] uppercase">{r.status}</span>
            </span>
            <span className="whitespace-nowrap font-mono">{inr(r.amount)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Timeline({ events, members, fresh }: { events: TimelineEvent[]; members: { member_id: string; name: string }[]; fresh: Set<string> }) {
  const name = (id: string) => first(members.find((m) => m.member_id === id)?.name ?? id);
  const dot: Record<string, string> = { update: "bg-gold", new_fact: "bg-accent", transaction: "bg-line" };
  return (
    <ol className="relative ml-2 border-l border-line">
      {events.map((e) => (
        <li key={e.record_id} className={`mb-3 ml-4 ${fresh.has(e.record_id) ? "fade-up" : ""}`}>
          <span className={`absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full ${dot[e.kind] ?? "bg-muted"} ${fresh.has(e.record_id) ? "pulse" : ""}`} />
          <div className={`rounded-lg px-3 py-2 ${fresh.has(e.record_id) ? "border border-accent/50 bg-accent/10" : e.kind === "transaction" ? "" : "bg-bg/40"}`}>
            <div className="flex items-center justify-between text-[10px] text-muted">
              <span>{fmtDate(e.date)} · {name(e.member_id)}</span>
              <span className="uppercase tracking-wide">{e.kind === "update" ? "superseded earlier fact" : e.kind.replace("_", " ")}</span>
            </div>
            <div className={`text-xs ${e.kind === "transaction" ? "text-muted" : ""}`}>{e.text}</div>
            <div className="text-[10px] text-muted">📄 {e.source}{e.superseded_record_id ? ` · replaces ${e.superseded_record_id} (kept in history)` : ""}</div>
          </div>
        </li>
      ))}
    </ol>
  );
}
