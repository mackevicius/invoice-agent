import { z } from 'zod';
import { request } from '@/lib/api';

const demoCompanySchema = z.object({
  id: z.uuid(),
  expires_at: z.iso.datetime(),
});

export type DemoCompany = z.infer<typeof demoCompanySchema>;

// The server returns the visitor's live Demo Company, or starts a new one.
export function startDemoCompany(): Promise<DemoCompany> {
  return request('/api/demo-company', demoCompanySchema, { method: 'POST' });
}
