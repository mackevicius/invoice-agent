"use client";
// PROTOTYPE Variant C: one narrow column, different per role.
// Submitter: a chat-like transcript of the agent's tool calls. Reviewer: one Invoice at a time (focus mode).
// Admin: a slider that previews which past Invoices the new limit would change.

import { useEffect, useState } from "react";
import { Bot, ExternalLink, FileText, Lock, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { caseOrder, eur, pct, PRICE_TOLERANCE_PCT, sampleCases, wouldAutoApprove } from "./demo-data";
import { demoCompanyNote, StatusBadge, StepIcon } from "./shared";
import { canDecide, type Demo, type InvoiceRecord, roles, traceHref, YOU } from "./use-demo";

export const name = "Conversation + focus";

export function VariantC({ demo }: { demo: Demo }) {
  return (
    <div className="min-h-screen bg-stone-50">
      <header className="sticky top-0 z-10 border-b bg-stone-50/90 backdrop-blur">
        <div className="mx-auto flex max-w-2xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <Bot className="size-5" />
            <span className="font-semibold">Invoice Agent</span>
          </div>
          <label className="flex items-center gap-2 text-sm">
            Viewing as
            <select
              value={demo.role}
              onChange={(e) => demo.setRole(e.target.value as (typeof roles)[number])}
              className="rounded-md border bg-background px-2 py-1"
            >
              {roles.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </label>
        </div>
        <p className="pb-2 text-center text-[11px] text-muted-foreground">{demoCompanyNote}</p>
      </header>
      <div className="mx-auto max-w-2xl px-4 pt-6 pb-28">
        {demo.role === "Submitter" && <Transcript demo={demo} />}
        {demo.role === "Reviewer" && <Focus demo={demo} />}
        {demo.role === "Admin" && <LimitPreview demo={demo} />}
      </div>
    </div>
  );
}

function Transcript({ demo }: { demo: Demo }) {
  const mine = demo.records.filter((r) => r.submittedBy === YOU).toReversed();
  const [dragging, setDragging] = useState(false);

  return (
    <div className="space-y-8">
      {mine.map((r) => (
        <Conversation key={r.id} record={r} />
      ))}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          demo.upload(undefined, e.dataTransfer.files[0]?.name);
        }}
        className={`sticky bottom-16 rounded-2xl border bg-background p-3 shadow-lg ${dragging ? "ring-2 ring-primary" : ""}`}
      >
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Upload className="size-4" /> Drop an Invoice (PDF or image) anywhere in this box, or send a sample:
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {caseOrder.map((k) => (
            <Button key={k} size="xs" variant="secondary" onClick={() => demo.upload(k)}>
              {sampleCases[k].label}
            </Button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Conversation({ record }: { record: InvoiceRecord }) {
  const { steps } = record.result;
  const done = record.status !== "running";
  return (
    <div className="space-y-3">
      <div className="ml-auto flex w-fit items-center gap-2 rounded-2xl rounded-br-sm bg-primary px-3 py-2 text-sm text-primary-foreground">
        <FileText className="size-4" /> {record.fileName}
        <span className="opacity-60">{record.submittedAt}</span>
      </div>
      <div className="space-y-1.5 rounded-2xl rounded-bl-sm border bg-background p-4">
        {steps.slice(0, record.stepsShown + (done ? 0 : 1)).map((s, i) => {
          const pending = i === record.stepsShown;
          if (s.title === "Decision") return null;
          return (
            <div key={s.title} className="flex gap-2 text-sm">
              <StepIcon status={pending ? "pending" : s.status} className="mt-0.5 size-4 shrink-0" />
              <div>
                {s.tool ? (
                  <code className="rounded bg-muted px-1 text-xs">{s.tool}</code>
                ) : (
                  <span className="font-medium">{s.title}</span>
                )}
                {!pending && <p className="text-muted-foreground">{s.summary}</p>}
              </div>
            </div>
          );
        })}
        {record.stepsShown > steps.findIndex((s) => s.title === "Match lines") && <LineSentences record={record} />}
        {done && (
          <div className="mt-3 border-t pt-3 text-sm">
            <div className="flex items-center justify-between">
              <StatusBadge status={record.status} />
              <a href={traceHref(record.id)} className="flex items-center gap-1 text-xs underline">
                Langfuse trace <ExternalLink className="size-3" />
              </a>
            </div>
            <p className="mt-2">
              {record.result.decision === "auto-approve"
                ? "Everything checks out, so I approved it."
                : "I sent it to the Review Queue because:"}
            </p>
            <ul className="list-disc pl-5">
              {record.result.reasons.map((r) => (
                <li key={r.text}>{r.text}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function LineSentences({ record, onlyProblems = false }: { record: InvoiceRecord; onlyProblems?: boolean }) {
  const lines = record.result.lines.filter((m) => !onlyProblems || !m.priceOk || !m.qtyOk);
  if (lines.length === 0) return null;
  return (
    <ul className="my-2 space-y-1 rounded-lg bg-muted/60 p-3 text-sm">
      {lines.map((m) => (
        <li key={m.sku}>
          <b>{m.description}</b>:{" "}
          {m.poPrice === null ? (
            <span className="text-red-700">not on the Purchase Order.</span>
          ) : (
            <>
              <span className={m.priceOk ? "" : "text-red-700"}>
                {eur(m.invoicePrice)} vs {eur(m.poPrice)} ordered
                {m.priceDiffPct !== 0 && ` (${pct(m.priceDiffPct!)}${m.priceOk ? ", within" : ", over"} ${PRICE_TOLERANCE_PCT}%)`}
              </span>
              ;{" "}
              <span className={m.qtyOk ? "" : "text-red-700"}>
                {m.invoiceQty} invoiced, {m.poQty} ordered, {m.receivedQty ?? 0} received
              </span>
              . {m.priceOk && m.qtyOk ? "✓" : ""}
            </>
          )}
        </li>
      ))}
    </ul>
  );
}

function Focus({ demo }: { demo: Demo }) {
  const [skipped, setSkipped] = useState<string[]>([]);
  const queue = demo.reviewQueue;
  const ordered = [...queue.filter((r) => !skipped.includes(r.id)), ...queue.filter((r) => skipped.includes(r.id))];
  const current = ordered[0];
  const [showAll, setShowAll] = useState(false);
  const gate = current ? canDecide(current, demo.role) : null;

  useEffect(() => {
    if (!current || !gate?.ok) return;
    function onKey(e: KeyboardEvent) {
      if ((e.target as HTMLElement | null)?.closest("input, textarea, select")) return;
      if (e.key === "a") demo.approve(current.id);
      if (e.key === "r") demo.reject(current.id);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, gate?.ok, demo]);

  if (!current) return <p className="py-20 text-center text-muted-foreground">The Review Queue is empty. Nice.</p>;

  return (
    <div className="space-y-4">
      <p className="text-center text-sm text-muted-foreground">
        Review Queue · {queue.length} waiting
      </p>
      <div className="space-y-5 rounded-3xl border bg-background p-6 shadow-sm">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm text-muted-foreground">{current.invoice.supplierName}</p>
            <p className="text-3xl font-semibold tabular-nums">{eur(current.result.total)}</p>
            <p className="text-sm text-muted-foreground">
              {current.invoice.number} · from {current.submittedBy}, {current.submittedAt}
            </p>
          </div>
          <a href={traceHref(current.id)} className="flex items-center gap-1 text-xs underline">
            Langfuse trace <ExternalLink className="size-3" />
          </a>
        </div>
        <div className="rounded-xl bg-amber-50 p-4 text-sm">
          <p className="mb-1 font-medium">The agent stopped because:</p>
          <ul className="list-disc pl-5">
            {current.result.reasons.map((r) => (
              <li key={r.text}>{r.text}</li>
            ))}
          </ul>
        </div>
        {current.result.lines.length > 0 && (
          <div>
            <LineSentences record={current} onlyProblems={!showAll} />
            <button className="text-xs underline" onClick={() => setShowAll(!showAll)}>
              {showAll ? "Only show problem lines" : `Show all ${current.result.lines.length} lines`}
            </button>
          </div>
        )}
        <p className="text-xs text-muted-foreground">
          Purchase Order {current.result.purchaseOrder?.number ?? "not found"} · Goods Receipt{" "}
          {current.result.goodsReceipt?.number ?? "not found"}
        </p>
        {gate?.ok ? (
          <div className="grid grid-cols-2 gap-3">
            <Button size="lg" variant="destructive" className="h-12" onClick={() => demo.reject(current.id)}>
              Reject <kbd className="opacity-60">R</kbd>
            </Button>
            <Button size="lg" className="h-12" onClick={() => demo.approve(current.id)}>
              Approve <kbd className="opacity-60">A</kbd>
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-2 rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
            <Lock className="size-4 shrink-0" /> {gate?.why}
          </div>
        )}
        <button
          className="w-full text-center text-xs text-muted-foreground underline"
          onClick={() => setSkipped([...skipped.filter((id) => id !== current.id), current.id])}
        >
          Skip for now
        </button>
      </div>
    </div>
  );
}

function LimitPreview({ demo }: { demo: Demo }) {
  const [draft, setDraft] = useState(demo.limit);
  const decided = demo.records.filter((r) => r.status !== "running");
  const changes = decided.filter((r) => wouldAutoApprove(r.result, draft) !== wouldAutoApprove(r.result, demo.limit));

  return (
    <div className="space-y-6 rounded-3xl border bg-background p-6">
      <div>
        <p className="text-sm text-muted-foreground">Auto-Approval Limit</p>
        <p className="text-4xl font-semibold tabular-nums">{eur(draft)}</p>
        <p className="text-xs text-muted-foreground">Saved: {eur(demo.limit)}. Applies to new Invoices only.</p>
      </div>
      <input
        type="range"
        min={0}
        max={20000}
        step={250}
        value={draft}
        onChange={(e) => setDraft(Number(e.target.value))}
        className="w-full"
      />
      <div className="text-sm">
        <p className="mb-2 font-medium">
          With this limit, {decided.filter((r) => wouldAutoApprove(r.result, draft)).length} of {decided.length} past
          Invoices would have been Auto-Approved.
        </p>
        {changes.length > 0 && (
          <ul className="space-y-1">
            {changes.map((r) => (
              <li key={r.id} className="flex justify-between rounded-md bg-muted px-3 py-1.5">
                <span>
                  {r.invoice.number} · {r.invoice.supplierName} · {eur(r.result.total)}
                </span>
                <span className={wouldAutoApprove(r.result, draft) ? "text-emerald-700" : "text-amber-700"}>
                  {wouldAutoApprove(r.result, draft) ? "now Auto-Approved" : "now goes to Review Queue"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <Button className="w-full" disabled={draft === demo.limit} onClick={() => demo.setLimit(draft)}>
        Save limit
      </Button>
    </div>
  );
}
