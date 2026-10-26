import { z } from 'zod';

const demoCompanySchema = z.object({
  id: z.uuid(),
  expires_at: z.iso.datetime(),
});

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
export type DemoCompany = z.infer<typeof demoCompanySchema>;

export class ApiError extends Error {}
export class DemoCompanyExpiredError extends ApiError {}
export class ServiceUnavailableError extends ApiError {}

async function request<Result>(
  path: string,
  schema: z.ZodType<Result>,
  options?: RequestInit,
): Promise<Result> {
  const response = await fetch(path, {
    ...options,
    credentials: 'same-origin',
    cache: 'no-store',
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new DemoCompanyExpiredError('This Demo Company has expired.');
    }
    if (response.status === 404) {
      throw new ApiError('This Invoice is no longer available.');
    }
    const message = 'The Invoice service is temporarily unavailable.';
    throw response.status >= 500
      ? new ServiceUnavailableError(message)
      : new ApiError(message);
  }

  const payload: unknown = await response.json().catch(() => null);
  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new ApiError('The Invoice service returned an invalid response.');
  }
  return parsed.data;
}

// The server returns the visitor's live Demo Company, or starts a new one.
export function startDemoCompany(): Promise<DemoCompany> {
  return request('/api/demo-company', demoCompanySchema, { method: 'POST' });
}

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
