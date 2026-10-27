import { z } from 'zod';
import { request } from '@/lib/api';

const decimalSchema = z.string().regex(/^\d+(?:\.\d+)?$/);

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
  fields: z
    .object({
      supplier_name: z.string(),
      invoice_number: z.string(),
      issued_on: z.iso.date(),
      currency: z.string(),
      lines: z.array(
        z.object({
          description: z.string(),
          quantity: decimalSchema,
          unit_price: decimalSchema,
        }),
      ),
      subtotal: decimalSchema,
      tax: decimalSchema,
      total: decimalSchema,
    })
    .nullable(),
  reasons: z.array(z.string()),
  steps: z.array(
    z.object({
      name: z.string(),
      status: z.enum(['Pending', 'Running', 'Completed', 'Failed', 'Skipped']),
      inputs: z.record(z.string(), z.json()),
      outputs: z.record(z.string(), z.json()).nullable(),
      started_at: z.iso.datetime({ offset: true }).nullable(),
      completed_at: z.iso.datetime({ offset: true }).nullable(),
    }),
  ),
});

export type InvoiceHeader = z.infer<typeof invoiceHeaderSchema>;
export type InvoiceDetail = z.infer<typeof invoiceDetailSchema>;

export function money(
  invoice: Pick<InvoiceHeader, 'total' | 'currency'>,
): string {
  if (invoice.total === null) return '-';
  return new Intl.NumberFormat('en-IE', {
    style: 'currency',
    currency: invoice.currency,
  }).format(Number(invoice.total));
}

export function listInvoices(signal: AbortSignal): Promise<InvoiceHeader[]> {
  return request('/api/invoices', z.array(invoiceHeaderSchema), { signal });
}

export function getInvoice(
  id: string,
  signal: AbortSignal,
): Promise<InvoiceDetail> {
  return request(
    `/api/invoices/${encodeURIComponent(id)}`,
    invoiceDetailSchema,
    { signal },
  );
}

export function uploadInvoice(file: File): Promise<InvoiceDetail> {
  const body = new FormData();
  body.append('file', file);
  return request('/api/invoices', invoiceDetailSchema, {
    method: 'POST',
    body,
  });
}
