export function inr(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Math.round(Number(v));
  return (n < 0 ? "-₹" : "₹") + Math.abs(n).toLocaleString("en-IN");
}

export function inrShort(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  const a = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  const trim = (x: number) => (Math.round(x * 100) / 100).toString();
  if (a >= 1e7) return `${sign}₹${trim(a / 1e7)} Cr`;
  if (a >= 1e5) return `${sign}₹${trim(a / 1e5)} L`;
  return sign + inr(a);
}

export const first = (name: string) => name.split(" ")[0];

export const fmtDate = (d: string) =>
  new Date(d + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
