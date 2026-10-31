import { z } from 'zod';
import { request } from '@/lib/api';

const demoCompanySchema = z.object({
  id: z.uuid(),
  expires_at: z.iso.datetime(),
});

const autoApprovalLimitSchema = z.object({
  amount: z.string().regex(/^\d{1,12}(?:\.\d{1,2})?$/),
  currency: z.literal('EUR'),
});

export type DemoCompany = z.infer<typeof demoCompanySchema>;
export type AutoApprovalLimit = z.infer<typeof autoApprovalLimitSchema>;

// The server returns the visitor's live Demo Company, or starts a new one.
export function startDemoCompany(): Promise<DemoCompany> {
  return request('/api/demo-company', demoCompanySchema, { method: 'POST' });
}

export function getAutoApprovalLimit(
  signal: AbortSignal,
): Promise<AutoApprovalLimit> {
  return request(
    '/api/demo-company/auto-approval-limit',
    autoApprovalLimitSchema,
    {
      signal,
      headers: { 'X-Demo-Role': 'Admin' },
    },
  );
}

export function setAutoApprovalLimit(
  amount: string,
): Promise<AutoApprovalLimit> {
  return request(
    '/api/demo-company/auto-approval-limit',
    autoApprovalLimitSchema,
    {
      method: 'PUT',
      headers: { 'X-Demo-Role': 'Admin', 'Content-Type': 'application/json' },
      body: JSON.stringify({ amount }),
    },
  );
}
