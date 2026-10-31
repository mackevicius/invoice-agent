import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { LoaderCircle, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ApiError, DemoCompanyExpiredError } from '@/lib/api';
import { setAutoApprovalLimit, type AutoApprovalLimit } from './api';

export function AutoApprovalLimitEditor({
  companyId,
  limit,
  disabled,
  onExpired,
}: {
  companyId: string;
  limit: AutoApprovalLimit | undefined;
  disabled: boolean;
  onExpired: (error: DemoCompanyExpiredError) => void;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);
  const save = useMutation({
    mutationFn: setAutoApprovalLimit,
    onSuccess: async (saved) => {
      await queryClient.cancelQueries({
        queryKey: ['demo-company', companyId, 'auto-approval-limit'],
      });
      queryClient.setQueryData(
        ['demo-company', companyId, 'auto-approval-limit'],
        saved,
      );
      setDraft(null);
      setInvalid(false);
    },
    onError: (error) => {
      if (error instanceof DemoCompanyExpiredError) onExpired(error);
    },
  });
  const value = draft ?? limit?.amount ?? '';
  const changed = limit !== undefined && Number(value) !== Number(limit.amount);
  const unavailable = disabled || limit === undefined || save.isPending;
  const current = limit
    ? new Intl.NumberFormat('en-IE', {
        style: 'currency',
        currency: limit.currency,
      }).format(Number(limit.amount))
    : null;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      !unavailable &&
      changed &&
      !invalid &&
      event.currentTarget.checkValidity()
    ) {
      save.mutate(value);
    }
  }

  return (
    <form
      aria-label="Auto-Approval Limit"
      aria-busy={limit === undefined || save.isPending}
      onSubmit={submit}
      className="grid gap-2"
    >
      <label
        htmlFor="auto-approval-limit"
        className="text-xs font-medium text-[#eef4f0]"
      >
        Auto-Approval Limit
      </label>
      <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
        <input
          id="auto-approval-limit"
          type="number"
          min="0"
          max="999999999999.99"
          step="0.01"
          required
          value={value}
          disabled={unavailable}
          onChange={(event) => {
            setDraft(event.currentTarget.value);
            setInvalid(!event.currentTarget.validity.valid);
            save.reset();
          }}
          className="h-8 w-full min-w-0 rounded-md border border-[#49584f] bg-[#252e28] px-2 font-mono text-xs text-[#eef4f0] outline-none focus-visible:ring-2 focus-visible:ring-[#a0d2b4] disabled:opacity-60"
        />
        <Button
          type="submit"
          size="sm"
          variant="secondary"
          aria-label="Save limit"
          disabled={unavailable || !changed || invalid}
          className="h-8 bg-[#eef4f0] text-[#191d1b] hover:bg-[#d8f0e2]"
        >
          {save.isPending ? (
            <LoaderCircle aria-hidden="true" className="animate-spin" />
          ) : (
            <Save aria-hidden="true" />
          )}
          Save
        </Button>
      </div>
      <p role="status" className="min-h-4 text-[11px] text-[#a7b7ad]">
        {current === null ? 'Loading limit...' : `Current limit ${current}`}
      </p>
      {save.error && !(save.error instanceof DemoCompanyExpiredError) && (
        <p role="alert" className="text-xs text-[#e08e85]">
          {save.error instanceof ApiError
            ? save.error.message
            : 'Unable to save the Auto-Approval Limit.'}
        </p>
      )}
    </form>
  );
}
