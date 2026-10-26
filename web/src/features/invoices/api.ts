import { z } from 'zod';
import { request } from '@/lib/api';

const invoiceHeaderSchema = z.object({
  id: z.uuid(),
  invoice_number: z.string().min(1),
  supplier: z.string().min(1),
  total: z.string().regex(/^\d+\.\d{2}$/),
  currency: z.literal('EUR'),
  status: z.enum([
    'Processing',
    'In Review',
    'Auto-Approved',
    'Approved',
    'Rejected',
  ]),
  issued_on: z.iso.date(),
});

export type InvoiceHeader = z.infer<typeof invoiceHeaderSchema>;

export function listInvoices(signal: AbortSignal): Promise<InvoiceHeader[]> {
  return request('/api/invoices', z.array(invoiceHeaderSchema), { signal });
}

export function getInvoice(
  id: string,
  signal: AbortSignal,
): Promise<InvoiceHeader> {
  return request(
    `/api/invoices/${encodeURIComponent(id)}`,
    invoiceHeaderSchema,
    { signal },
  );
}
