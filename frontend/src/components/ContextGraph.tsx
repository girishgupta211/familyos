"use client";
import { useMemo, useState } from "react";
import type { GEdge, GNode, Graph } from "@/lib/api";
import { inrShort } from "@/lib/fmt";

const KIND_STYLE: Record<string, { color: string; icon: string; label: string }> = {
  family: { color: "#e6ebf5", icon: "⌂", label: "Family" },
  member: { color: "#34d399", icon: "●", label: "Member" },
  employer: { color: "#60a5fa", icon: "₹", label: "Income source" },
  income: { color: "#60a5fa", icon: "₹", label: "Other income" },
  bank_account: { color: "#a78bfa", icon: "▣", label: "Bank account" },
  investment_portfolio: { color: "#22d3ee", icon: "▲", label: "Investments" },
  property: { color: "#f5b544", icon: "⌂", label: "Property" },
  loan_account: { color: "#f87171", icon: "−", label: "Loan" },
  insurance_policy: { color: "#f0abfc", icon: "♦", label: "Insurance" },
  expense: { color: "#fb923c", icon: "↘", label: "Expense" },
  tax: { color: "#94a3b8", icon: "§", label: "Tax" },
  pension_source: { color: "#60a5fa", icon: "₹", label: "Income source" },
  business: { color: "#38bdf8", icon: "◼", label: "Business" },
  deposit: { color: "#a78bfa", icon: "▣", label: "Deposit / FD" },
  retirement_account: { color: "#818cf8", icon: "⧗", label: "Locked / retirement" },
  vehicle: { color: "#f5b544", icon: "◒", label: "Vehicle" },
  precious_metal: { color: "#facc15", icon: "◆", label: "Gold" },
  credit_card: { color: "#f87171", icon: "▭", label: "Credit card" },
};
const style = (k: string) => KIND_STYLE[k] ?? { color: "#94a3b8", icon: "•", label: k };

const W = 760, H = 640, CX = W / 2, CY = H / 2;

export default function ContextGraph({ graph: input, onSelect }: { graph: Graph; onSelect?: (n: GNode) => void }) {
  let graph = input;
  const [hover, setHover] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);

  // Derived kinship (siblings, grandparents) stays in Neo4j for queries but is hidden here to keep the picture readable.
  const shown = useMemo(() => ({ ...input, edges: input.edges.filter((e) => !["sibling_of", "grandparent_of"].includes(e.type)) }), [input]);
  graph = shown;
  const pos = useMemo(() => layout(shown), [shown]);
  const focus = hover ?? sel;
  const linked = useMemo(() => {
    if (!focus) return null;
    const s = new Set([focus]);
    graph.edges.forEach((e) => {
      if (e.from === focus) s.add(e.to);
      if (e.to === focus) s.add(e.from);
    });
    return s;
  }, [focus, graph.edges]);

  const kinds = Array.from(new Set(graph.nodes.map((n) => style(n.kind).label === "Member" ? "member" : n.kind)))
    .filter((k) => k !== "family")
    .filter((k, i, arr) => arr.findIndex((x) => style(x).label === style(k).label) === i);
  const dense = graph.nodes.filter((n) => n.kind !== "member" && n.kind !== "family").length > 22;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none">
        <defs>
          <radialGradient id="glow">
            <stop offset="0%" stopColor="#34d399" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#34d399" stopOpacity="0" />
          </radialGradient>
        </defs>
        <circle cx={CX} cy={CY} r={memberR(graph)} fill="url(#glow)" />
        <circle cx={CX} cy={CY} r={memberR(graph)} fill="none" stroke="#1c2740" strokeDasharray="3 5" />
        <circle cx={CX} cy={CY} r={OUTER_R} fill="none" stroke="#1c2740" strokeDasharray="3 5" />
        {graph.edges.map((e, i) => {
          const a = pos[e.from], b = pos[e.to];
          if (!a || !b) return null;
          const dim = linked && !(linked.has(e.from) && linked.has(e.to));
          const family = ["spouse_of", "parent_of", "sibling_of", "grandparent_of", "supports"].includes(e.type);
          const color = family ? "#34d399" : e.type.includes("owe") ? "#f87171" : "#3b4a6b";
          const d = family
            ? `M${a.x},${a.y} Q${(a.x + b.x) / 2 + (CX - (a.x + b.x) / 2) * 0.6},${(a.y + b.y) / 2 + (CY - (a.y + b.y) / 2) * 0.6} ${b.x},${b.y}`
            : `M${a.x},${a.y} L${b.x},${b.y}`;
          return (
            <g key={i} opacity={dim ? 0.12 : 1} style={{ transition: "opacity .2s" }}>
              <path d={d} fill="none" stroke={color} strokeWidth={family ? 1.8 : 1.2}
                strokeDasharray={e.type.startsWith("co_") || ["nominee_of", "secured_against", "covered_by", "pays_for", "guardian_of"].includes(e.type) ? "4 4" : undefined} />
              {linked && !dim && e.type !== "has_member" && (
                <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 3} fontSize="9" fill="#8a96b0" textAnchor="middle">
                  {e.type.replace(/_/g, " ")}
                </text>
              )}
            </g>
          );
        })}
        {graph.nodes.map((n) => {
          const p = pos[n.id];
          if (!p) return null;
          const s = style(n.kind);
          const r = n.kind === "family" ? 26 : n.kind === "member" ? 22 : dense ? 11 : 14;
          const dim = linked && !linked.has(n.id);
          const showLabel = n.kind === "member" || n.kind === "family" || !dense || (linked?.has(n.id) ?? false);
          return (
            <g key={n.id} transform={`translate(${p.x},${p.y})`} opacity={dim ? 0.2 : 1}
              style={{ cursor: "pointer", transition: "opacity .2s" }}
              onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}
              onClick={() => { setSel(sel === n.id ? null : n.id); onSelect?.(n); }}>
              <circle r={r + 4} fill={s.color} opacity={sel === n.id ? 0.25 : 0} />
              <circle r={r} fill="#0d1424" stroke={s.color} strokeWidth={n.kind === "member" ? 2.5 : 1.5} />
              <text textAnchor="middle" dy="0.35em" fontSize={n.kind === "member" ? 13 : 11} fill={s.color} fontWeight={600}>
                {n.kind === "member" ? n.label[0] : s.icon}
              </text>
              {showLabel && <text textAnchor="middle" y={r + 12} fontSize={n.kind === "member" ? 11 : 9} fill="#e6ebf5" fontWeight={n.kind === "member" ? 600 : 400}>
                {short(n.label)}
              </text>}
              {showLabel && n.value && (
                <text textAnchor="middle" y={r + 23} fontSize="9" fill={s.color}>
                  {inrShort(n.value)}{n.record_type === "income" || n.record_type === "expense" ? "/mo" : ""}
                </text>
              )}
              {n.role && <text textAnchor="middle" y={r + 23} fontSize="9" fill="#8a96b0">{n.role}</text>}
            </g>
          );
        })}
      </svg>
      <div className="flex flex-wrap gap-x-3 gap-y-1 px-1 text-[11px] text-muted">
        {kinds.map((k) => (
          <span key={k} className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: style(k).color }} />
            {style(k).label}
          </span>
        ))}
        <span className="flex items-center gap-1"><span className="inline-block h-px w-4 border-t border-dashed border-muted" /> joint / nominee / covered</span>
        {dense && <span className="text-muted/80">· hover a member to reveal labels</span>}
      </div>
    </div>
  );
}

function short(s: string) {
  const t = s.replace(/^[A-Z][a-z]+ — /, "").replace(/ Pvt Ltd| Analytics/g, "");
  return t.length > 20 ? t.slice(0, 19) + "…" : t;
}

const OUTER_R = 250;
const memberR = (g: Graph) => (g.nodes.filter((n) => n.kind === "member").length > 4 ? 135 : 110);

function layout(g: Graph): Record<string, { x: number; y: number }> {
  const pos: Record<string, { x: number; y: number }> = {};
  const fam = g.nodes.find((n) => n.kind === "family");
  if (fam) pos[fam.id] = { x: CX, y: CY };
  const members = g.nodes.filter((n) => n.kind === "member");
  const mR = memberR(g);
  const ang: Record<string, number> = {};
  members.forEach((m, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / members.length;
    ang[m.id] = a;
    pos[m.id] = { x: CX + mR * Math.cos(a), y: CY + mR * Math.sin(a) };
  });
  const owners = (id: string) =>
    g.edges.filter((e: GEdge) => e.to === id && ang[e.from] !== undefined &&
      !["nominee_of", "covered_by", "pays_for", "guardian_of"].includes(e.type)).map((e) => e.from);
  const groups: Record<string, GNode[]> = {};
  g.nodes.filter((n) => n.kind !== "member" && n.kind !== "family").forEach((n) => {
    const o = owners(n.id);
    const key = o.length ? o.sort().join("+") : "none";
    (groups[key] ??= []).push(n);
  });
  const budget = (2 * Math.PI) / Math.max(members.length, 1);
  Object.entries(groups).forEach(([key, nodes]) => {
    const os = key.split("+").filter((k) => ang[k] !== undefined);
    let base: number;
    if (os.length === 0) base = Math.PI / 2;
    else if (os.length === 1) base = ang[os[0]];
    else {
      const sx = os.reduce((s, o) => s + Math.cos(ang[o]), 0), sy = os.reduce((s, o) => s + Math.sin(ang[o]), 0);
      base = Math.atan2(sy, sx);
    }
    const joint = os.length > 1;
    const rings = nodes.length > 6 ? 3 : nodes.length > 3 ? 2 : 1;
    const perRing = Math.ceil(nodes.length / rings);
    const spread = Math.min(joint ? 0.42 : 0.5, (budget * (joint ? 0.45 : 0.8)) / Math.max(perRing, 1));
    nodes.forEach((n, i) => {
      const ring = i % rings, k = Math.floor(i / rings);
      const a = base + (k - (perRing - 1) / 2) * spread + (ring ? spread / 2 : 0);
      const r = (joint ? mR + 70 : OUTER_R - 40) + ring * 38;
      pos[n.id] = { x: CX + r * Math.cos(a), y: CY + r * Math.sin(a) };
    });
  });
  return pos;
}
