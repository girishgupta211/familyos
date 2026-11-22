export let FAMILY = "F001";
export const setFamily = (f: string) => { FAMILY = f; };

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

const q = (m?: string | null) => (m ? `?member_id=${m}` : "");

export const api = {
  health: () => fetch(`/api/health?family_id=${FAMILY}`, { cache: "no-store" }).then(j<Health>),
  families: () => fetch("/api/families", { cache: "no-store" }).then(j<FamilyInfo[]>),
  overview: (m?: string | null) => fetch(`/api/family/${FAMILY}/overview${q(m)}`, { cache: "no-store" }).then(j<Overview>),
  graph: (m?: string | null) => fetch(`/api/family/${FAMILY}/graph${q(m)}`, { cache: "no-store" }).then(j<Graph>),
  context: (m?: string | null) => fetch(`/api/family/${FAMILY}/context${q(m)}`, { cache: "no-store" }).then(j<ContextB>),
  ask: (question: string, member_id: string | null, history: { role: string; content: string }[]) =>
    fetch(`/api/family/${FAMILY}/ask`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question, member_id, history }),
    }).then(j<Answer>),
  askStream: async (
    question: string, member_id: string | null, history: { role: string; content: string }[],
    onTrace: (t: TraceEvent) => void,
    familyId: string = FAMILY,
  ): Promise<Answer> => {
    const res = await fetch(`/api/family/${familyId}/ask/stream`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question, member_id, history }),
    });
    if (!res.ok || !res.body) throw new Error(`${res.status}: ${await res.text()}`);
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, i);
        buf = buf.slice(i + 2);
        const line = chunk.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        const ev = JSON.parse(line.slice(6));
        if (ev.type === "trace") onTrace(ev);
        else if (ev.type === "answer") return ev.data as Answer;
      }
    }
    throw new Error("Stream ended without an answer");
  },
  ingest: (records: unknown[]) =>
    fetch(`/api/family/${FAMILY}/records`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ schema_version: "1.0", family_id: FAMILY, financial_records: records }),
    }).then(j<{ accepted: string[]; memory_changes: TimelineEvent[] }>),
  reset: () => fetch(`/api/family/${FAMILY}/reset`, { method: "POST" }).then(j),
};

export type Neo4jStatus = { connected: boolean; nodes: number; relationships: number; last_sync: string | null; private_records_excluded?: number; browser: string; error: string | null };
export type Health = { ok: boolean; llm: boolean; model: string | null; mode: string; speed?: string | null; effort?: string | null; neo4j?: Neo4jStatus };
export type FamilyInfo = { family_id: string; name: string; city?: string; summary?: string; default_member_id?: string; questions: string[]; member_count?: number; record_count?: number };
export type TraceEvent = { node: string; ms: number; detail: string; kind?: string };
export type Member = { member_id: string; name: string; relationship: string; date_of_birth?: string };
export type Holding = { record_id: string; type: string; category: string; label: string; amount: string | null; frequency: string | null; emi?: string | null };
export type Overview = {
  family_id: string;
  summary: Record<string, string | null> & { income_by_member: Record<string, string>; missing: string[] };
  members: (Member & { monthly_income: string; holdings: Holding[] })[];
  goals: Goal[];
  withheld_record_count: number;
};
export type Goal = { kind: string; label: string; amount: string; target_date: string; created_at: string };
export type GNode = { id: string; kind: string; label: string; role?: string; value?: string | null; record_type?: string; record_ids?: string[] };
export type GEdge = { from: string; to: string; type: string };
export type Graph = { nodes: GNode[]; edges: GEdge[] };
export type TimelineEvent = { date: string; member_id: string; kind: string; type: string; text: string; record_id: string; superseded_record_id: string | null; source: string };
export type Fact = { record_id: string; member_id: string; type: string; category: string; description: string; amount: string | null; frequency: string | null; status: string; valid_from: string; source: { filename: string; document_id: string }; confidence: number; superseded_by: string | null; supersedes: string | null; entity_id: string };
export type ContextB = { members: Member[]; memory_timeline: TimelineEvent[]; financial_context: Fact[]; withheld_record_count: number; goals: Goal[] };
export type Calc = { label: string; formula: string; result: string; value: string; record_ids: string[] };
export type SupportingRecord = { record_id: string; member: string; type: string; category: string; description: string; amount: string | null; frequency: string | null; status: string; valid_from: string; confidence: number; source: { filename: string; document_id: string; document_type?: string } };
export type Answer = {
  answer: string;
  key_findings: string[];
  context_insights: string[];
  supporting_records: SupportingRecord[];
  calculations: Calc[];
  assumptions: string[];
  missing_information: string[];
  confidence: "high" | "medium" | "low";
  verification: { checks: { check: string; ok: boolean; detail?: string }[]; narrator: string; narrative_grounded: boolean; ungrounded_numbers_rejected: string[]; low_confidence_record_ids: string[]; self_corrections?: number };
  mode?: string;
  model?: string;
  intent: string;
  plan: Record<string, unknown>;
  withheld_record_count: number;
  live_sources?: { tool: string; args: Record<string, unknown>; ms: number; source: string }[];
  remembered_goals: Goal[];
  trace: TraceEvent[];
};
