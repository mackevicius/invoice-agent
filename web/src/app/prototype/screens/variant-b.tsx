"use client";
// PROTOTYPE Variant B: split view. One list of every Invoice on the left, one detail pane on the right.
// Steps are a horizontal pipeline; lines are one unified grid; Admin lives in the sidebar footer.

import { useState } from "react";
import { ExternalLink, Lock, Plus, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { caseOrder, eur, pct, PRICE_TOLERANCE_PCT, reasonLabel, sampleCases } from "./demo-data";
import { demoCompanyNote, StatusBadge, StepIcon } from "./shared";
import { canDecide, type Demo, type InvoiceRecord, roles, type Status, traceHref, YOU } from "./use-demo";

export const name = "Split view";

type Filter = "all" | "mine" | "queue" | "done";
const filters: { key: Filter; label: string; test: (r: InvoiceRecord) => boolean }[] = [
  { key: "all", label: "All", test: () => true },
  { key: "mine", label: "Mine", test: (r) => r.submittedBy === YOU },
  { key: "queue", label: "Review Queue", test: (r) => r.status === "in-review" },
  { key: "done", label: "Done", test: (r) => (["auto-approved", "approved", "rejected"] as Status[]).includes(r.status) },
];

const dot: Record<Status, string> = {
  running: "bg-sky-500 animate-pulse",
  "auto-approved": "bg-emerald-500",
  "in-review": "bg-amber-500",
  approved: "bg-emerald-700",
  rejected: "bg-red-600",
};

export function VariantB({ demo }: { demo: Demo }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const list = demo.records.filter(filters.find((f) => f.key === filter)!.test);
  const selected = demo.records.find((r) => r.id === selectedId) ?? list[0];
  const showUpload = uploading && demo.role === "Submitter";

  const upload = (key?: (typeof caseOrder)[number], file?: string) => {
    setSelectedId(demo.upload(key, file));
    setUploading(false);
    setFilter("mine");
  };

  return (
    <div className="grid h-screen grid-cols-[340px_1fr] overflow-hidden">
      <aside className="flex flex-col border-r bg-zinc-950 text-zinc-100">
        <div className="space-y-3 border-b border-zinc-800 p-4">
          <div>
            <p className="font-semibold">Invoice Agent</p>
            <p className="text-xs text-zinc-400">{demoCompanyNote}</p>
          </div>
          <div className="text-xs">
            <p className="mb-1 text-zinc-400">Viewing as</p>
            <div className="grid grid-cols-3 gap-1 rounded-lg bg-zinc-900 p-1">
              {roles.map((r) => (
                <button
                  key={r}
                  onClick={() => {
                    demo.setRole(r);
                    setFilter(r === "Reviewer" ? "queue" : r === "Submitter" ? "mine" : "all");
                  }}
                  className={`rounded-md py-1 ${demo.role === r ? "bg-zinc-100 text-zinc-900" : "text-zinc-300 hover:bg-zinc-800"}`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
          {demo.role === "Submitter" && (
            <Button
              className={`w-full ${showUpload ? "ring-2 ring-zinc-100" : ""}`}
              variant="secondary"
              onClick={() => setUploading(true)}
            >
              <Plus /> Upload Invoice
            </Button>
          )}
        </div>

        <div role="tablist" className="flex border-b border-zinc-800 px-2 pt-2 text-xs">
          {filters.map((f) => {
            const active = filter === f.key;
            return (
              <button
                key={f.key}
                role="tab"
                aria-selected={active}
                onClick={() => setFilter(f.key)}
                className={`relative flex flex-1 items-center justify-center gap-1.5 px-1 pt-2 pb-2.5 font-medium whitespace-nowrap transition-colors ${active ? "text-zinc-50" : "text-zinc-500 hover:text-zinc-200"}`}
              >
                {f.label}
                <span
                  className={`rounded-full px-1.5 text-[10px] tabular-nums ${active ? "bg-zinc-100 text-zinc-900" : "bg-zinc-800 text-zinc-400"}`}
                >
                  {demo.records.filter(f.test).length}
                </span>
                <span
                  className={`absolute inset-x-1 -bottom-px h-0.5 rounded-full transition-colors ${active ? "bg-zinc-100" : "bg-transparent"}`}
                />
              </button>
            );
          })}
        </div>

        <ul className="flex-1 space-y-0.5 overflow-y-auto p-2">
          {list.map((r) => (
            <li key={r.id}>
              <button
                onClick={() => {
                  setSelectedId(r.id);
                  setUploading(false);
                }}
                className={`w-full rounded-md px-3 py-2 text-left text-sm ${!showUpload && selected?.id === r.id ? "bg-zinc-800" : "hover:bg-zinc-900"}`}
              >
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <span className={`size-2 rounded-full ${dot[r.status]}`} />
                    {r.invoice.number}
                  </span>
                  <span className="tabular-nums text-zinc-300">{eur(r.result.total)}</span>
                </div>
                <div className="flex justify-between pl-4 text-xs text-zinc-400">
                  <span>{r.invoice.supplierName}</span>
                  <span>
                    {r.status === "running"
                      ? `step ${r.stepsShown + 1}/${r.result.steps.length}`
                      : r.result.reasons.length > 0
                        ? `${r.result.reasons.length} reason(s)`
                        : "clean"}
                  </span>
                </div>
              </button>
            </li>
          ))}
        </ul>

        {demo.role === "Admin" && <AdminFooter demo={demo} />}
      </aside>

      <main className="overflow-y-auto bg-background pb-24">
        {showUpload ? (
          <UploadPage onUpload={upload} />
        ) : selected ? (
          <Detail demo={demo} record={selected} />
        ) : (
          <p className="p-10 text-muted-foreground">Nothing here.</p>
        )}
      </main>
    </div>
  );
}

function UploadPage({ onUpload }: { onUpload: (key?: (typeof caseOrder)[number], file?: string) => void }) {
  const [dragging, setDragging] = useState(false);
  return (
    <div className="mx-auto max-w-2xl space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Upload an Invoice</h1>
        <p className="text-sm text-muted-foreground">
          The agent reads it, runs the Three-Way Match against the ERP, checks for a Duplicate Invoice, and either
          Auto-Approves it or sends it to the Review Queue. You can watch every step.
        </p>
      </div>
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          onUpload(undefined, e.dataTransfer.files[0]?.name);
        }}
        className={`flex h-72 cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed text-center ${dragging ? "border-primary bg-primary/5" : "bg-muted/30 hover:bg-muted/50"}`}
      >
        <Upload className="size-10 text-muted-foreground" />
        <span className="text-lg font-medium">Drop an Invoice here</span>
        <span className="text-sm text-muted-foreground">or click to choose a file · PDF or image</span>
        <input
          type="file"
          accept="application/pdf,image/*"
          className="hidden"
          onChange={(e) => onUpload(undefined, e.target.files?.[0]?.name)}
        />
      </label>
      <div>
        <p className="mb-2 text-sm text-muted-foreground">No Invoice to hand? Try a sample:</p>
        <div className="grid grid-cols-3 gap-2">
          {caseOrder.map((k) => (
            <Button key={k} variant="outline" onClick={() => onUpload(k)}>
              {sampleCases[k].label}
            </Button>
          ))}
        </div>
      </div>
    </div>
  );
}

function AdminFooter({ demo }: { demo: Demo }) {
  const [draft, setDraft] = useState(String(demo.limit));
  return (
    <div className="space-y-2 border-t border-zinc-800 p-4 text-xs">
      <p className="font-medium">Auto-Approval Limit</p>
      <div className="flex gap-2">
        <Input
          type="number"
          step={500}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="border-zinc-700 bg-zinc-900 text-zinc-100"
        />
        <Button size="sm" variant="secondary" disabled={Number(draft) === demo.limit} onClick={() => demo.setLimit(Number(draft) || 0)}>
          Save
        </Button>
      </div>
      <p className="text-zinc-400">Now {eur(demo.limit)}. Applies to new Invoices.</p>
    </div>
  );
}

function Detail({ demo, record }: { demo: Demo; record: InvoiceRecord }) {
  const { result } = record;
  const gate = canDecide(record, demo.role);
  const done = record.status !== "running";
  const showLines = result.lines.length > 0 && record.stepsShown >= result.steps.findIndex((s) => s.title === "Match lines") + 1;

  return (
    <div className="space-y-8 p-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold">{record.invoice.number}</h1>
            <StatusBadge status={record.status} />
          </div>
          <p className="text-sm text-muted-foreground">
            {record.invoice.supplierName} · {eur(result.total)} · {record.fileName} · submitted by {record.submittedBy},{" "}
            {record.submittedAt} ·{" "}
            <a href={traceHref(record.id)} className="inline-flex items-center gap-0.5 underline">
              Langfuse trace <ExternalLink className="size-3" />
            </a>
          </p>
        </div>
        {demo.role === "Reviewer" && record.status === "in-review" && (
          <div className="flex shrink-0 items-center gap-2">
            {gate.ok ? (
              <>
                <Button variant="destructive" onClick={() => demo.reject(record.id)}>
                  Reject
                </Button>
                <Button onClick={() => demo.approve(record.id)}>Approve</Button>
              </>
            ) : (
              <span className="flex max-w-64 items-center gap-2 rounded-lg border border-dashed px-3 py-2 text-xs text-muted-foreground">
                <Lock className="size-4 shrink-0" /> {gate.why}
              </span>
            )}
          </div>
        )}
      </div>

      <ol className="flex items-start">
        {result.steps.map((s, i) => {
          const state = i < record.stepsShown ? s.status : i === record.stepsShown ? "pending" : null;
          return (
            <li key={s.title} className="flex flex-1 flex-col items-center gap-1 text-center">
              <div className="flex w-full items-center">
                <span className={`h-px flex-1 ${i === 0 ? "" : "bg-border"}`} />
                <span className={`rounded-full border-2 p-1 ${state ? "border-transparent" : "border-dashed"}`}>
                  {state ? <StepIcon status={state} className="size-6" /> : <span className="block size-6" />}
                </span>
                <span className={`h-px flex-1 ${i === result.steps.length - 1 ? "" : "bg-border"}`} />
              </div>
              <span className="text-xs font-medium">{s.title}</span>
              {state && state !== "pending" && <span className="px-1 text-[11px] leading-tight text-muted-foreground">{s.summary}</span>}
            </li>
          );
        })}
      </ol>

      {showLines && (
        <div className="overflow-hidden rounded-xl border">
          <table className="w-full text-sm">
            <thead className="bg-muted/60 text-xs text-muted-foreground">
              <tr>
                <th rowSpan={2} className="p-2 text-left">Line</th>
                <th colSpan={2} className="border-l p-1">Invoice</th>
                <th colSpan={2} className="border-l p-1">Purchase Order {result.purchaseOrder?.number}</th>
                <th className="border-l p-1">Goods Receipt {result.goodsReceipt?.number}</th>
                <th rowSpan={2} className="border-l p-2">Result</th>
              </tr>
              <tr>
                <th className="border-l p-1">Qty</th>
                <th className="p-1">Price</th>
                <th className="border-l p-1">Qty</th>
                <th className="p-1">Price</th>
                <th className="border-l p-1">Received</th>
              </tr>
            </thead>
            <tbody>
              {result.lines.map((m) => {
                const qtyBad = !m.qtyOk ? "bg-red-50 text-red-700 font-semibold" : "";
                const priceBad = !m.priceOk ? "bg-red-50 text-red-700 font-semibold" : "";
                return (
                  <tr key={m.sku} className="border-t text-center tabular-nums">
                    <td className="p-2 text-left">{m.description}</td>
                    <td className={`border-l p-2 ${qtyBad}`}>{m.invoiceQty}</td>
                    <td className={`p-2 ${priceBad}`}>{eur(m.invoicePrice)}</td>
                    <td className={`border-l p-2 ${qtyBad}`}>{m.poQty ?? "—"}</td>
                    <td className={`p-2 ${priceBad}`}>{m.poPrice === null ? "—" : eur(m.poPrice)}</td>
                    <td className={`border-l p-2 ${qtyBad}`}>{m.receivedQty ?? "—"}</td>
                    <td className="border-l p-2 text-xs">
                      {m.priceOk && m.qtyOk ? (
                        <span className="text-emerald-700">match</span>
                      ) : (
                        <span className="text-red-700">
                          {!m.priceOk && m.priceDiffPct !== null && `price ${pct(m.priceDiffPct)} (max ${PRICE_TOLERANCE_PCT}%)`}
                          {!m.priceOk && !m.qtyOk && " · "}
                          {!m.qtyOk && "quantity"}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {done && result.reasons.length > 0 && (
        <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          {result.reasons.map((r) => (
            <div key={r.text} className="contents">
              <span className="font-medium text-amber-800">{reasonLabel[r.code]}</span>
              <span>{r.text}</span>
            </div>
          ))}
        </div>
      )}
      {done && result.reasons.length === 0 && (
        <p className="text-sm text-emerald-700">
          Known Supplier, Three-Way Match passes, not a Duplicate Invoice, total under {eur(demo.limit)}.
        </p>
      )}
    </div>
  );
}
