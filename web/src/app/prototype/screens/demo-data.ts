// PROTOTYPE: fake ERP data and a fake agent. Throw away once the screens are decided.

export type CaseKey =
  | "clean"
  | "price"
  | "quantity"
  | "duplicate"
  | "unknown-supplier"
  | "over-limit";

export type InvoiceLine = { sku: string; description: string; qty: number; unitPrice: number };

export type Invoice = {
  number: string;
  supplierName: string;
  purchaseOrderRef: string | null;
  date: string;
  lines: InvoiceLine[];
};

export type Supplier = { id: string; name: string };
export type PurchaseOrder = { number: string; supplierId: string; lines: InvoiceLine[] };
export type GoodsReceipt = {
  number: string;
  purchaseOrder: string;
  lines: { sku: string; qtyReceived: number }[];
};

const suppliers: Supplier[] = [
  { id: "S-101", name: "Nordic Office Supplies" },
  { id: "S-204", name: "Baltic Steel" },
  { id: "S-310", name: "Riga Packaging" },
];

const purchaseOrders: PurchaseOrder[] = [
  {
    number: "PO-5512",
    supplierId: "S-101",
    lines: [{ sku: "CH-01", description: "Office chair", qty: 4, unitPrice: 189 }],
  },
  {
    number: "PO-5530",
    supplierId: "S-101",
    lines: [
      { sku: "PA-A4", description: "A4 paper, box", qty: 40, unitPrice: 24.5 },
      { sku: "TN-22", description: "Toner cartridge", qty: 6, unitPrice: 62 },
    ],
  },
  {
    number: "PO-6120",
    supplierId: "S-204",
    lines: [
      { sku: "SH-2", description: "Steel sheet 2 mm", qty: 120, unitPrice: 18 },
      { sku: "BM-8", description: "Bolts M8, box", qty: 30, unitPrice: 12 },
    ],
  },
  {
    number: "PO-6155",
    supplierId: "S-204",
    lines: [
      { sku: "BE-6", description: "Steel beam 6 m", qty: 40, unitPrice: 310 },
      { sku: "WR-3", description: "Welding rods, pack", qty: 50, unitPrice: 24 },
    ],
  },
  {
    number: "PO-7004",
    supplierId: "S-310",
    lines: [
      { sku: "BX-40", description: "Shipping box 40 cm", qty: 500, unitPrice: 1.2 },
      { sku: "TP-50", description: "Packing tape", qty: 100, unitPrice: 2.4 },
    ],
  },
];

const goodsReceipts: GoodsReceipt[] = [
  { number: "GR-8801", purchaseOrder: "PO-5512", lines: [{ sku: "CH-01", qtyReceived: 4 }] },
  {
    number: "GR-8820",
    purchaseOrder: "PO-5530",
    lines: [
      { sku: "PA-A4", qtyReceived: 40 },
      { sku: "TN-22", qtyReceived: 6 },
    ],
  },
  {
    number: "GR-9102",
    purchaseOrder: "PO-6120",
    lines: [
      { sku: "SH-2", qtyReceived: 120 },
      { sku: "BM-8", qtyReceived: 30 },
    ],
  },
  {
    number: "GR-9140",
    purchaseOrder: "PO-6155",
    lines: [
      { sku: "BE-6", qtyReceived: 40 },
      { sku: "WR-3", qtyReceived: 50 },
    ],
  },
  {
    number: "GR-9311",
    purchaseOrder: "PO-7004",
    lines: [
      { sku: "BX-40", qtyReceived: 450 },
      { sku: "TP-50", qtyReceived: 100 },
    ],
  },
];

export const PRICE_TOLERANCE_PCT = 2;
export const DEFAULT_LIMIT = 5000;

export const sampleCases: Record<CaseKey, { label: string; invoice: Invoice }> = {
  clean: {
    label: "Clean match",
    invoice: {
      number: "INV-1077",
      supplierName: "Nordic Office Supplies",
      purchaseOrderRef: "PO-5530",
      date: "2026-10-22",
      lines: [
        { sku: "PA-A4", description: "A4 paper, box", qty: 40, unitPrice: 24.5 },
        { sku: "TN-22", description: "Toner cartridge", qty: 6, unitPrice: 62 },
      ],
    },
  },
  price: {
    label: "Price over 2%",
    invoice: {
      number: "INV-2231",
      supplierName: "Baltic Steel",
      purchaseOrderRef: "PO-6120",
      date: "2026-10-23",
      lines: [
        { sku: "SH-2", description: "Steel sheet 2 mm", qty: 120, unitPrice: 18.9 },
        { sku: "BM-8", description: "Bolts M8, box", qty: 30, unitPrice: 12.1 },
      ],
    },
  },
  quantity: {
    label: "Quantity mismatch",
    invoice: {
      number: "INV-3308",
      supplierName: "Riga Packaging",
      purchaseOrderRef: "PO-7004",
      date: "2026-10-23",
      lines: [
        { sku: "BX-40", description: "Shipping box 40 cm", qty: 500, unitPrice: 1.2 },
        { sku: "TP-50", description: "Packing tape", qty: 100, unitPrice: 2.4 },
      ],
    },
  },
  duplicate: {
    label: "Duplicate Invoice",
    invoice: {
      number: "INV-1042",
      supplierName: "Nordic Office Supplies",
      purchaseOrderRef: "PO-5512",
      date: "2026-10-19",
      lines: [{ sku: "CH-01", description: "Office chair", qty: 4, unitPrice: 189 }],
    },
  },
  "unknown-supplier": {
    label: "Unknown Supplier",
    invoice: {
      number: "INV-77",
      supplierName: "Vilnius Print House",
      purchaseOrderRef: null,
      date: "2026-10-24",
      lines: [{ sku: "BR-A5", description: "Brochures A5", qty: 1000, unitPrice: 0.45 }],
    },
  },
  "over-limit": {
    label: "Total over limit",
    invoice: {
      number: "INV-2240",
      supplierName: "Baltic Steel",
      purchaseOrderRef: "PO-6155",
      date: "2026-10-24",
      lines: [
        { sku: "BE-6", description: "Steel beam 6 m", qty: 40, unitPrice: 310 },
        { sku: "WR-3", description: "Welding rods, pack", qty: 50, unitPrice: 24 },
      ],
    },
  },
};

export const caseOrder: CaseKey[] = [
  "clean",
  "price",
  "quantity",
  "duplicate",
  "unknown-supplier",
  "over-limit",
];

export type StepStatus = "ok" | "warn" | "fail" | "skipped";
export type Step = { title: string; tool: string | null; status: StepStatus; summary: string };

export type LineMatch = {
  sku: string;
  description: string;
  invoiceQty: number;
  invoicePrice: number;
  poQty: number | null;
  poPrice: number | null;
  receivedQty: number | null;
  priceDiffPct: number | null;
  priceOk: boolean;
  qtyOk: boolean;
};

export type ReasonCode =
  | "unknown-supplier"
  | "no-purchase-order"
  | "no-goods-receipt"
  | "not-on-purchase-order"
  | "price"
  | "quantity"
  | "duplicate"
  | "over-limit";

export type Reason = { code: ReasonCode; text: string };

export type AgentResult = {
  steps: Step[];
  supplier: Supplier | null;
  purchaseOrder: PurchaseOrder | null;
  goodsReceipt: GoodsReceipt | null;
  lines: LineMatch[];
  duplicateOf: string | null;
  reasons: Reason[];
  decision: "auto-approve" | "review";
  total: number;
};

export const reasonLabel: Record<ReasonCode, string> = {
  "unknown-supplier": "Unknown Supplier",
  "no-purchase-order": "No Purchase Order",
  "no-goods-receipt": "No Goods Receipt",
  "not-on-purchase-order": "Line not on Purchase Order",
  price: "Price over tolerance",
  quantity: "Quantity mismatch",
  duplicate: "Duplicate Invoice",
  "over-limit": "Over Auto-Approval Limit",
};

const eurFormat = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" });
export const eur = (n: number) => eurFormat.format(n);
export const pct = (n: number) => `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;

export const invoiceTotal = (invoice: Invoice) =>
  invoice.lines.reduce((sum, l) => sum + l.qty * l.unitPrice, 0);

export type PriorInvoice = { number: string; supplierName: string; submittedAt: string };

export function runAgent(invoice: Invoice, prior: PriorInvoice[], limit: number): AgentResult {
  const steps: Step[] = [];
  const reasons: Reason[] = [];
  const total = invoiceTotal(invoice);

  steps.push({
    title: "Read Invoice",
    tool: "read_invoice(file)",
    status: "ok",
    summary: `${invoice.number} from ${invoice.supplierName}: ${invoice.lines.length} line(s), total ${eur(total)}`,
  });

  const supplier =
    suppliers.find((s) => s.name.toLowerCase() === invoice.supplierName.toLowerCase()) ?? null;
  if (supplier) {
    steps.push({
      title: "Find Supplier",
      tool: `erp.find_supplier({ name: "${invoice.supplierName}" })`,
      status: "ok",
      summary: `Found ${supplier.name} (${supplier.id})`,
    });
  } else {
    steps.push({
      title: "Find Supplier",
      tool: `erp.find_supplier({ name: "${invoice.supplierName}" })`,
      status: "fail",
      summary: `No Supplier called "${invoice.supplierName}" in the ERP`,
    });
    reasons.push({
      code: "unknown-supplier",
      text: `"${invoice.supplierName}" is not a known Supplier`,
    });
  }

  const purchaseOrder =
    supplier && invoice.purchaseOrderRef
      ? (purchaseOrders.find(
          (p) => p.number === invoice.purchaseOrderRef && p.supplierId === supplier.id,
        ) ?? null)
      : null;
  if (!supplier) {
    steps.push({ title: "Find Purchase Order", tool: null, status: "skipped", summary: "Skipped: no Supplier" });
  } else if (!purchaseOrder) {
    steps.push({
      title: "Find Purchase Order",
      tool: `erp.get_purchase_order({ number: "${invoice.purchaseOrderRef}" })`,
      status: "fail",
      summary: `No Purchase Order ${invoice.purchaseOrderRef ?? "(none on Invoice)"} for this Supplier`,
    });
    reasons.push({ code: "no-purchase-order", text: "No matching Purchase Order" });
  } else {
    steps.push({
      title: "Find Purchase Order",
      tool: `erp.get_purchase_order({ number: "${purchaseOrder.number}" })`,
      status: "ok",
      summary: `${purchaseOrder.number}: ${purchaseOrder.lines.length} line(s)`,
    });
  }

  const goodsReceipt = purchaseOrder
    ? (goodsReceipts.find((g) => g.purchaseOrder === purchaseOrder.number) ?? null)
    : null;
  if (!purchaseOrder) {
    steps.push({ title: "Find Goods Receipt", tool: null, status: "skipped", summary: "Skipped: no Purchase Order" });
  } else if (!goodsReceipt) {
    steps.push({
      title: "Find Goods Receipt",
      tool: `erp.get_goods_receipt({ purchaseOrder: "${purchaseOrder.number}" })`,
      status: "fail",
      summary: "Nothing has arrived yet",
    });
    reasons.push({ code: "no-goods-receipt", text: "No Goods Receipt: goods have not arrived" });
  } else {
    steps.push({
      title: "Find Goods Receipt",
      tool: `erp.get_goods_receipt({ purchaseOrder: "${purchaseOrder.number}" })`,
      status: "ok",
      summary: `${goodsReceipt.number}: goods arrived`,
    });
  }

  const lines: LineMatch[] = [];
  if (!purchaseOrder) {
    steps.push({ title: "Match lines", tool: null, status: "skipped", summary: "Skipped: nothing to match against" });
  } else {
    for (const l of invoice.lines) {
      const poLine = purchaseOrder.lines.find((p) => p.sku === l.sku) ?? null;
      const grLine = goodsReceipt?.lines.find((g) => g.sku === l.sku) ?? null;
      const priceDiffPct = poLine ? ((l.unitPrice - poLine.unitPrice) / poLine.unitPrice) * 100 : null;
      const priceOk = priceDiffPct !== null && Math.abs(priceDiffPct) <= PRICE_TOLERANCE_PCT;
      const qtyOk = !!poLine && l.qty === poLine.qty && grLine?.qtyReceived === l.qty;
      lines.push({
        sku: l.sku,
        description: l.description,
        invoiceQty: l.qty,
        invoicePrice: l.unitPrice,
        poQty: poLine?.qty ?? null,
        poPrice: poLine?.unitPrice ?? null,
        receivedQty: grLine?.qtyReceived ?? null,
        priceDiffPct,
        priceOk,
        qtyOk,
      });
      if (!poLine) {
        reasons.push({ code: "not-on-purchase-order", text: `${l.description} is not on the Purchase Order` });
        continue;
      }
      if (!priceOk && priceDiffPct !== null) {
        reasons.push({
          code: "price",
          text: `${l.description}: ${eur(l.unitPrice)} vs ${eur(poLine.unitPrice)} on the Purchase Order (${pct(priceDiffPct)}, tolerance ${PRICE_TOLERANCE_PCT}%)`,
        });
      }
      if (!qtyOk) {
        reasons.push({
          code: "quantity",
          text: `${l.description}: invoiced ${l.qty}, ordered ${poLine.qty}, received ${grLine?.qtyReceived ?? 0}`,
        });
      }
    }
    const bad = lines.filter((m) => !m.priceOk || !m.qtyOk).length;
    steps.push({
      title: "Match lines",
      tool: null,
      status: bad === 0 ? "ok" : "fail",
      summary: bad === 0 ? `All ${lines.length} line(s) pass the Three-Way Match` : `${bad} of ${lines.length} line(s) fail the Three-Way Match`,
    });
  }

  let duplicateOf: string | null = null;
  if (!supplier) {
    steps.push({ title: "Duplicate check", tool: null, status: "skipped", summary: "Skipped: no Supplier" });
  } else {
    const dup = prior.find(
      (p) => p.number === invoice.number && p.supplierName.toLowerCase() === invoice.supplierName.toLowerCase(),
    );
    duplicateOf = dup ? dup.number : null;
    steps.push({
      title: "Duplicate check",
      tool: `erp.find_invoices({ supplier: "${supplier.id}", number: "${invoice.number}" })`,
      status: dup ? "fail" : "ok",
      summary: dup ? `Already received ${dup.number} on ${dup.submittedAt}` : "No earlier Invoice with this number",
    });
    if (dup) reasons.push({ code: "duplicate", text: `Same as ${dup.number} received ${dup.submittedAt}` });
  }

  if (total > limit) {
    reasons.push({
      code: "over-limit",
      text: `Total ${eur(total)} is over the Auto-Approval Limit of ${eur(limit)}`,
    });
  }
  const decision = reasons.length === 0 ? "auto-approve" : "review";
  steps.push({
    title: "Decision",
    tool: null,
    status: decision === "auto-approve" ? "ok" : "warn",
    summary:
      decision === "auto-approve"
        ? `Auto-Approved (total under ${eur(limit)})`
        : `Sent to the Review Queue: ${reasons.length} reason(s)`,
  });

  return { steps, supplier, purchaseOrder, goodsReceipt, lines, duplicateOf, reasons, decision, total };
}

export function wouldAutoApprove(result: AgentResult, limit: number) {
  return result.reasons.every((r) => r.code === "over-limit") && result.total <= limit;
}
