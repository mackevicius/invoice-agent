import { z } from 'zod';
import { request } from '@/lib/api';

export const demoRoles = ['Submitter', 'Reviewer', 'Admin'] as const;
export type DemoRole = (typeof demoRoles)[number];
export type InvoiceView = 'all' | 'mine' | 'review-queue' | 'done';
export type InvoiceDecision =
  { action: 'approve' } | { action: 'reject'; rejectionReason: string };

const invoiceCountsSchema = z.object({
  all: z.number().int().nonnegative(),
  mine: z.number().int().nonnegative(),
  review_queue: z.number().int().nonnegative(),
  done: z.number().int().nonnegative(),
});

const decimalSchema = z.string().regex(/^\d+(?:\.\d+)?$/);
const signedDecimalSchema = z.string().regex(/^-?\d+(?:\.\d+)?$/);
const invoiceLineSchema = z.object({
  description: z.string(),
  item_code: z.string().nullable(),
  quantity: decimalSchema,
  unit_price: decimalSchema,
});

const invoiceHeaderSchema = z.object({
  id: z.uuid(),
  invoice_number: z.string().min(1).nullable(),
  supplier: z.string().min(1).nullable(),
  total: decimalSchema.nullable(),
  currency: z.string().regex(/^[A-Z]{3}$/),
  status: z.enum([
    'Processing',
    'In Review',
    'Auto-Approved',
    'Approved',
    'Rejected',
  ]),
  issued_on: z.iso.date().nullable(),
});

const invoiceDetailSchema = invoiceHeaderSchema.extend({
  filename: z.string().nullable(),
  submitted_by: z.string(),
  rejection_reason: z.string().nullable(),
  can_decide: z.boolean(),
  decision_block_reason: z.string().nullable(),
  fields: z
    .object({
      supplier_name: z.string(),
      invoice_number: z.string(),
      purchase_order_number: z.string().nullable(),
      issued_on: z.iso.date(),
      currency: z.string(),
      lines: z.array(invoiceLineSchema),
      subtotal: decimalSchema,
      tax: decimalSchema,
      total: decimalSchema,
    })
    .nullable(),
  comparison: z.array(
    z.object({
      line_number: z.number().int().positive(),
      invoice: invoiceLineSchema,
      purchase_order: invoiceLineSchema.extend({ id: z.uuid() }).nullable(),
      goods_receipt: z
        .object({
          purchase_order_line_id: z.uuid(),
          quantity: decimalSchema,
        })
        .nullable(),
      paired_by: z.enum(['item_code', 'description']).nullable(),
      unit_price_difference: signedDecimalSchema.nullable(),
      unit_price_difference_percent: signedDecimalSchema.nullable(),
      price_passed: z.boolean(),
      quantity_passed: z.boolean(),
      mismatched_cells: z.array(
        z.enum([
          'invoice.description',
          'invoice.quantity',
          'invoice.unit_price',
          'purchase_order.description',
          'purchase_order.quantity',
          'purchase_order.unit_price',
          'goods_receipt.quantity',
        ]),
      ),
      reasons: z.array(z.string()),
    }),
  ),
  reasons: z.array(z.string()),
  steps: z.array(
    z.object({
      name: z.string(),
      status: z.enum(['Pending', 'Running', 'Completed', 'Failed', 'Skipped']),
      inputs: z.record(z.string(), z.json()),
      outputs: z
        .object({
          duplicates: z
            .array(
              z.object({
                invoice_id: z.uuid(),
                invoice_number: z.string(),
                reason: z.string(),
              }),
            )
            .optional(),
        })
        .catchall(z.json())
        .nullable(),
      started_at: z.iso.datetime({ offset: true }).nullable(),
      completed_at: z.iso.datetime({ offset: true }).nullable(),
    }),
  ),
});

export type InvoiceHeader = z.infer<typeof invoiceHeaderSchema>;
export type InvoiceDetail = z.infer<typeof invoiceDetailSchema>;
export type LineComparison = InvoiceDetail['comparison'][number];

export function money(
  invoice: Pick<InvoiceHeader, 'total' | 'currency'>,
): string {
  if (invoice.total === null) return '-';
  return new Intl.NumberFormat('en-IE', {
    style: 'currency',
    currency: invoice.currency,
  }).format(Number(invoice.total));
}

export function listInvoices(
  signal: AbortSignal,
  role: DemoRole = 'Submitter',
  view: InvoiceView = 'all',
): Promise<InvoiceHeader[]> {
  return request(`/api/invoices?view=${view}`, z.array(invoiceHeaderSchema), {
    signal,
    headers: { 'X-Demo-Role': role },
  });
}

export function getInvoiceCounts(signal: AbortSignal, role: DemoRole) {
  return request('/api/invoices/counts', invoiceCountsSchema, {
    signal,
    headers: { 'X-Demo-Role': role },
  });
}

export function getInvoice(
  id: string,
  signal: AbortSignal,
  role: DemoRole = 'Submitter',
): Promise<InvoiceDetail> {
  return request(
    `/api/invoices/${encodeURIComponent(id)}`,
    invoiceDetailSchema,
    { signal, headers: { 'X-Demo-Role': role } },
  );
}

export function uploadInvoice(
  file: File,
  role: DemoRole = 'Submitter',
): Promise<InvoiceDetail> {
  const body = new FormData();
  body.append('file', file);
  return request('/api/invoices', invoiceDetailSchema, {
    method: 'POST',
    body,
    headers: { 'X-Demo-Role': role },
  });
}

export function decideInvoice(
  id: string,
  role: DemoRole,
  decision: InvoiceDecision,
): Promise<InvoiceDetail> {
  return request(
    `/api/invoices/${encodeURIComponent(id)}/${decision.action}`,
    invoiceDetailSchema,
    {
      method: 'POST',
      headers: { 'X-Demo-Role': role, 'Content-Type': 'application/json' },
      body:
        decision.action === 'reject'
          ? JSON.stringify({ rejection_reason: decision.rejectionReason })
          : undefined,
    },
  );
}
