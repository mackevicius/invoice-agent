import type { z } from 'zod';

export class ApiError extends Error {}
export class DemoCompanyExpiredError extends ApiError {}
export class ServiceUnavailableError extends ApiError {}

export async function request<Result>(
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
