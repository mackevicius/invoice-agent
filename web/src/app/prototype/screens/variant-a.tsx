"use client";
// PROTOTYPE Variant A: classic app. Tabs for every screen (locked by role), Review Queue as a table,
// detail shows Invoice | Purchase Order | Goods Receipt as three documents side by side.

import { useState } from "react";
import { ArrowLeft, ExternalLink, Lock, Upload } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { caseOrder, eur, pct, reasonLabel, sampleCases } from "./demo-data";
import { demoCompanyNote, StatusBadge, StepIcon } from "./shared";
import { canDecide, type Demo, type InvoiceRecord, type Role, roles, traceHref, YOU } from "./use-demo";

type Tab = "upload" | "queue" | "admin";
const tabForRole: Record<Role, Tab> = { Submitter: "upload", Reviewer: "queue", Admin: "admin" };
const roleForTab: Record<Tab, Role> = { upload: "Submitter", queue: "Reviewer", admin: "Admin" };

export const name = "Tabs + documents";

export function VariantA({ demo }: { demo: Demo }) {
  const [tab, setTab] = useState<Tab>(tabForRole[demo.role]);

  return (
    <div className="min-h-screen bg-muted/40 pb-24">
      <header className="flex items-center justify-between border-b bg-background px-6 py-3">
        <div className="flex items-center gap-3">
          <span className="font-semibold">Invoice Agent</span>
          <Badge variant="outline">{demoCompanyNote}</Badge>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Viewing as:</span>
          {roles.map((r) => (
            <Button
              key={r}
              size="sm"
              variant={demo.role === r ? "default" : "outline"}
              onClick={() => {
                demo.setRole(r);
                setTab(tabForRole[r]);
              }}
            >
              {r}
            </Button>
          ))}
        </div>
      </header>

      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="mx-auto max-w-6xl px-6 pt-4">
        <TabsList variant="line">
          <TabsTrigger value="upload">Upload</TabsTrigger>
          <TabsTrigger value="queue">Review Queue ({demo.reviewQueue.length})</TabsTrigger>
          <TabsTrigger value="admin">Admin</TabsTrigger>
        </TabsList>
        {(["upload", "queue", "admin"] as Tab[]).map((t) => (
          <TabsContent key={t} value={t} className="pt-4">
            {demo.role !== roleForTab[t] ? (
              <Locked need={roleForTab[t]} onSwitch={() => demo.setRole(roleForTab[t])} />
            ) : t === "upload" ? (
              <UploadScreen demo={demo} />
            ) : t === "queue" ? (
              <QueueScreen demo={demo} />
            ) : (
              <AdminScreen demo={demo} />
            )}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}

function Locked({ need, onSwitch }: { need: Role; onSwitch: () => void }) {
  return (
    <Card className="items-center py-16 text-center">
      <Lock className="size-6 text-muted-foreground" />
      <p className="text-sm text-muted-foreground">This screen is for the {need}.</p>
      <Button variant="outline" onClick={onSwitch}>
        View as {need}
      </Button>
    </Card>
  );
}

function UploadScreen({ demo }: { demo: Demo }) {
  const mine = demo.records.filter((r) => r.submittedBy === YOU);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const selected = mine.find((r) => r.id === selectedId) ?? mine[0];

  return (
    <div className="grid grid-cols-[320px_1fr] gap-6">
      <div className="space-y-4">
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            setSelectedId(demo.upload(undefined, e.dataTransfer.files[0]?.name));
          }}
          className={`flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed bg-background p-8 text-center text-sm ${dragging ? "border-primary bg-primary/5" : ""}`}
        >
          <Upload className="size-6 text-muted-foreground" />
          <span className="font-medium">Drop an Invoice here</span>
          <span className="text-muted-foreground">PDF or image</span>
          <input
            type="file"
            accept="application/pdf,image/*"
            className="hidden"
            onChange={(e) => setSelectedId(demo.upload(undefined, e.target.files?.[0]?.name))}
          />
        </label>
        <div>
          <p className="mb-2 text-xs text-muted-foreground">Or try a sample:</p>
          <div className="flex flex-wrap gap-1.5">
            {caseOrder.map((k) => (
              <Button key={k} size="xs" variant="outline" onClick={() => setSelectedId(demo.upload(k))}>
                {sampleCases[k].label}
              </Button>
            ))}
          </div>
        </div>
        <Card size="sm">
          <CardHeader>
            <CardTitle>Your Invoices</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {mine.map((r) => (
              <button
                key={r.id}
                onClick={() => setSelectedId(r.id)}
                className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted ${selected?.id === r.id ? "bg-muted" : ""}`}
              >
                <span>
                  {r.invoice.number} <span className="text-muted-foreground">· {r.invoice.supplierName}</span>
                </span>
                <StatusBadge status={r.status} />
              </button>
            ))}
          </CardContent>
        </Card>
      </div>
      {selected ? <LiveSteps record={selected} /> : null}
    </div>
  );
}

function LiveSteps({ record }: { record: InvoiceRecord }) {
  const { steps } = record.result;
  const shown = steps.slice(0, record.stepsShown);
  const matchShown = shown.some((s) => s.title === "Match lines" && s.status !== "skipped");
  const done = record.stepsShown >= steps.length;

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {record.invoice.number} · {record.invoice.supplierName}
        </CardTitle>
        <CardDescription>
          {record.fileName} · submitted {record.submittedAt}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <ol className="relative space-y-4 border-l pl-6">
          {steps.map((s, i) => {
            const state = i < record.stepsShown ? s.status : i === record.stepsShown ? "pending" : null;
            if (!state) return null;
            return (
              <li key={s.title} className="relative">
                <span className="absolute top-0.5 -left-[33px] rounded-full bg-background p-0.5">
                  <StepIcon status={state} />
                </span>
                <p className="text-sm font-medium">{s.title}</p>
                {state === "pending" ? (
                  <p className="text-sm text-muted-foreground">Working…</p>
                ) : (
                  <>
                    <p className="text-sm text-muted-foreground">{s.summary}</p>
                    {s.tool && <code className="text-xs text-muted-foreground/80">{s.tool}</code>}
                  </>
                )}
              </li>
            );
          })}
        </ol>

        {matchShown && <LineTable record={record} />}

        {done && (
          <div
            className={`rounded-lg border p-4 ${record.result.decision === "auto-approve" ? "border-emerald-300 bg-emerald-50" : "border-amber-300 bg-amber-50"}`}
          >
            <div className="flex items-center justify-between">
              <StatusBadge status={record.status} />
              <a href={traceHref(record.id)} className="flex items-center gap-1 text-xs underline">
                Langfuse trace <ExternalLink className="size-3" />
              </a>
            </div>
            {record.result.reasons.length > 0 && (
              <ul className="mt-2 list-disc pl-5 text-sm">
                {record.result.reasons.map((r) => (
                  <li key={r.text}>{r.text}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function LineTable({ record }: { record: InvoiceRecord }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Line</TableHead>
          <TableHead className="text-right">Invoice</TableHead>
          <TableHead className="text-right">Purchase Order</TableHead>
          <TableHead className="text-right">Price diff</TableHead>
          <TableHead className="text-right">Received</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {record.result.lines.map((m) => (
          <TableRow key={m.sku}>
            <TableCell>{m.description}</TableCell>
            <TableCell className="text-right">
              {m.invoiceQty} × {eur(m.invoicePrice)}
            </TableCell>
            <TableCell className="text-right">
              {m.poQty === null ? "—" : `${m.poQty} × ${eur(m.poPrice!)}`}
            </TableCell>
            <TableCell className={`text-right ${m.priceOk ? "" : "font-semibold text-red-600"}`}>
              {m.priceDiffPct === null ? "—" : pct(m.priceDiffPct)}
            </TableCell>
            <TableCell className={`text-right ${m.qtyOk ? "" : "font-semibold text-red-600"}`}>
              {m.receivedQty ?? "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function QueueScreen({ demo }: { demo: Demo }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const open = demo.records.find((r) => r.id === openId);
  if (open) return <ReviewDetail demo={demo} record={open} onBack={() => setOpenId(null)} />;

  return (
    <Card>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="pl-4">Invoice</TableHead>
            <TableHead>Supplier</TableHead>
            <TableHead className="text-right">Total</TableHead>
            <TableHead>Submitted by</TableHead>
            <TableHead>Reasons</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {demo.reviewQueue.map((r) => (
            <TableRow key={r.id} onClick={() => setOpenId(r.id)} className="cursor-pointer">
              <TableCell className="pl-4 font-medium">{r.invoice.number}</TableCell>
              <TableCell>{r.invoice.supplierName}</TableCell>
              <TableCell className="text-right tabular-nums">{eur(r.result.total)}</TableCell>
              <TableCell>
                {r.submittedBy} <span className="text-muted-foreground">· {r.submittedAt}</span>
              </TableCell>
              <TableCell className="flex flex-wrap gap-1">
                {[...new Set(r.result.reasons.map((x) => x.code))].map((c) => (
                  <Badge key={c} variant="secondary">
                    {reasonLabel[c]}
                  </Badge>
                ))}
              </TableCell>
            </TableRow>
          ))}
          {demo.reviewQueue.length === 0 && (
            <TableRow>
              <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">
                The Review Queue is empty.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </Card>
  );
}

function ReviewDetail({ demo, record, onBack }: { demo: Demo; record: InvoiceRecord; onBack: () => void }) {
  const { result } = record;
  const gate = canDecide(record, demo.role);
  const bad = (sku: string, field: "price" | "qty") => {
    const m = result.lines.find((l) => l.sku === sku);
    return m ? (field === "price" ? !m.priceOk : !m.qtyOk) : true;
  };
  const cell = (isBad: boolean) => (isBad ? "bg-red-100 font-semibold text-red-700" : "");

  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" onClick={onBack}>
        <ArrowLeft /> Review Queue
      </Button>
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-semibold">
            {record.invoice.number} · {record.invoice.supplierName} · {eur(result.total)}
          </h2>
          <p className="text-sm text-muted-foreground">
            Submitted by {record.submittedBy}, {record.submittedAt} ·{" "}
            <a href={traceHref(record.id)} className="underline">
              Langfuse trace
            </a>
          </p>
        </div>
        <StatusBadge status={record.status} />
      </div>
      <Card size="sm" className="border-amber-300 bg-amber-50">
        <CardContent>
          <p className="mb-1 text-sm font-medium">Why the agent did not approve it</p>
          <ul className="list-disc pl-5 text-sm">
            {result.reasons.map((r) => (
              <li key={r.text}>{r.text}</li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <div className="grid grid-cols-3 gap-4">
        <DocCard title="Invoice" subtitle={record.invoice.number}>
          {record.invoice.lines.map((l) => (
            <DocRow key={l.sku} label={l.description}>
              <span className={cell(bad(l.sku, "qty"))}>{l.qty}</span> ×{" "}
              <span className={cell(bad(l.sku, "price"))}>{eur(l.unitPrice)}</span>
            </DocRow>
          ))}
        </DocCard>
        <DocCard title="Purchase Order" subtitle={result.purchaseOrder?.number ?? "Not found"}>
          {result.purchaseOrder?.lines.map((l) => (
            <DocRow key={l.sku} label={l.description}>
              {l.qty} × <span className={cell(bad(l.sku, "price"))}>{eur(l.unitPrice)}</span>
            </DocRow>
          ))}
        </DocCard>
        <DocCard title="Goods Receipt" subtitle={result.goodsReceipt?.number ?? "Not found"}>
          {result.goodsReceipt?.lines.map((l) => (
            <DocRow key={l.sku} label={result.lines.find((m) => m.sku === l.sku)?.description ?? l.sku}>
              <span className={cell(bad(l.sku, "qty"))}>{l.qtyReceived}</span> received
            </DocRow>
          ))}
        </DocCard>
      </div>

      <div className="sticky bottom-20 flex items-center justify-end gap-3 rounded-xl border bg-background p-3 shadow-sm">
        {gate.why && (
          <span className="mr-auto flex items-center gap-2 text-sm text-muted-foreground">
            <Lock className="size-4" /> {gate.why}
          </span>
        )}
        <Button variant="destructive" disabled={!gate.ok} onClick={() => (demo.reject(record.id), onBack())}>
          Reject
        </Button>
        <Button disabled={!gate.ok} onClick={() => (demo.approve(record.id), onBack())}>
          Approve
        </Button>
      </div>
    </div>
  );
}

function DocCard({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{subtitle}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">{children}</CardContent>
    </Card>
  );
}

function DocRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-2 border-b pb-2 text-sm last:border-0">
      <span>{label}</span>
      <span className="tabular-nums">{children}</span>
    </div>
  );
}

function AdminScreen({ demo }: { demo: Demo }) {
  const [draft, setDraft] = useState(String(demo.limit));
  const auto = demo.records.filter((r) => r.status === "auto-approved").length;

  return (
    <Card className="max-w-lg">
      <CardHeader>
        <CardTitle>Auto-Approval Limit</CardTitle>
        <CardDescription>
          The agent approves an Invoice on its own only if the total is under this amount (and the Supplier is known,
          the Three-Way Match passes, and it is not a Duplicate Invoice). Applies to new Invoices.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <span className="flex items-center text-sm text-muted-foreground">€</span>
          <Input type="number" min={0} step={500} value={draft} onChange={(e) => setDraft(e.target.value)} />
          <Button onClick={() => demo.setLimit(Number(draft) || 0)} disabled={Number(draft) === demo.limit}>
            Save
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">
          Current limit: <b className="text-foreground">{eur(demo.limit)}</b> · {auto} Invoice(s) Auto-Approved ·{" "}
          {demo.reviewQueue.length} in the Review Queue
        </p>
      </CardContent>
    </Card>
  );
}
