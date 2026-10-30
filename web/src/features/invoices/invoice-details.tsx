import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react';
import Link from 'next/link';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Check,
  Circle,
  CircleMinus,
  LoaderCircle,
  LockKeyhole,
  TriangleAlert,
  X,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ApiError, DemoCompanyExpiredError } from '@/lib/api';
import {
  decideInvoice,
  money,
  type DemoRole,
  type InvoiceDecision,
  type InvoiceDetail,
  type LineComparison,
} from './api';
import styles from './split-view.module.css';

export const statusClass: Record<InvoiceDetail['status'], string> = {
  Processing: styles.processing,
  'In Review': styles.review,
  'Auto-Approved': styles.autoApproved,
  Approved: styles.approved,
  Rejected: styles.rejected,
};

function ComparisonCell({
  line,
  field,
  children,
}: {
  line: LineComparison;
  field: LineComparison['mismatched_cells'][number];
  children: ReactNode;
}) {
  const mismatched = line.mismatched_cells.includes(field);
  return (
    <td data-mismatch={mismatched}>
      {mismatched && <span className="sr-only">Mismatch: </span>}
      {children}
    </td>
  );
}

function ComparisonLine({
  line,
  currency,
}: {
  line: LineComparison;
  currency: string;
}) {
  const passed = line.price_passed && line.quantity_passed;
  const Icon = passed ? Check : TriangleAlert;
  const quantity = (value: string | undefined) =>
    value === undefined
      ? '-'
      : new Intl.NumberFormat('en-IE', { maximumFractionDigits: 3 }).format(
          Number(value),
        );
  return (
    <div
      className={styles.linesScroll}
      role="region"
      aria-label={`Line ${line.line_number} comparison scroll area`}
      tabIndex={0}
    >
      <table aria-label={`Line ${line.line_number} comparison`}>
        <caption>
          <div className={styles.comparisonCaption}>
            <span>Line {line.line_number}</span>
            <span className={passed ? styles.linePassed : styles.lineFailed}>
              <Icon size={14} aria-hidden="true" />
              {passed ? 'Passed' : 'Mismatch'}
            </span>
          </div>
        </caption>
        <thead>
          <tr>
            <th scope="col">Field</th>
            <th scope="col">Invoice</th>
            <th scope="col">Purchase Order</th>
            <th scope="col">Goods Receipt</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Item</th>
            <ComparisonCell line={line} field="invoice.description">
              {line.invoice.description}
              {line.invoice.item_code && (
                <span className={styles.itemCode}>
                  {line.invoice.item_code}
                </span>
              )}
            </ComparisonCell>
            <ComparisonCell line={line} field="purchase_order.description">
              {line.purchase_order?.description ?? 'Not paired'}
              {line.purchase_order?.item_code && (
                <span className={styles.itemCode}>
                  {line.purchase_order.item_code}
                </span>
              )}
            </ComparisonCell>
            <td>
              {line.goods_receipt
                ? line.purchase_order?.description
                : 'Not received'}
            </td>
          </tr>
          <tr>
            <th scope="row">Quantity</th>
            <ComparisonCell line={line} field="invoice.quantity">
              {quantity(line.invoice.quantity)}
            </ComparisonCell>
            <ComparisonCell line={line} field="purchase_order.quantity">
              {quantity(line.purchase_order?.quantity)}
            </ComparisonCell>
            <ComparisonCell line={line} field="goods_receipt.quantity">
              {quantity(line.goods_receipt?.quantity)}
            </ComparisonCell>
          </tr>
          <tr>
            <th scope="row">Unit price</th>
            <ComparisonCell line={line} field="invoice.unit_price">
              {money({ total: line.invoice.unit_price, currency })}
            </ComparisonCell>
            <ComparisonCell line={line} field="purchase_order.unit_price">
              {money({
                total: line.purchase_order?.unit_price ?? null,
                currency,
              })}
            </ComparisonCell>
            <td>-</td>
          </tr>
          <tr>
            <th scope="row">Price difference</th>
            <td>
              {money({ total: line.unit_price_difference, currency })}
              {line.unit_price_difference_percent !== null && (
                <span className={styles.priceDifference}>
                  {Number(line.unit_price_difference_percent) > 0 ? '+' : ''}
                  {line.unit_price_difference_percent}%
                </span>
              )}
            </td>
            <td>-</td>
            <td>-</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function InvoiceDetails({
  invoice,
  role,
  onDecided,
  onOpenInvoice,
  onExpired,
}: {
  invoice: InvoiceDetail;
  role: DemoRole;
  onDecided: (invoice: InvoiceDetail) => void;
  onOpenInvoice: (invoiceId: string) => void;
  onExpired: (error: DemoCompanyExpiredError) => void;
}) {
  const queryClient = useQueryClient();
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState('');
  const reasonInput = useRef<HTMLTextAreaElement>(null);
  const rejectButton = useRef<HTMLButtonElement>(null);
  const duplicates =
    invoice.steps.find(
      (step) => step.name === 'Check Duplicates' && step.status === 'Completed',
    )?.outputs?.duplicates ?? [];
  const decision = useMutation({
    mutationFn: (command: InvoiceDecision) =>
      decideInvoice(invoice.id, role, command),
    onSuccess: (result) => {
      setRejectOpen(false);
      setReason('');
      onDecided(result);
    },
    onError: (error) => {
      if (error instanceof DemoCompanyExpiredError) onExpired(error);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ['invoices'] });
    },
  });

  useEffect(() => {
    if (rejectOpen) reasonInput.current?.focus();
  }, [rejectOpen]);

  function reject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (reason.trim() && !decision.isPending) {
      decision.mutate({ action: 'reject', rejectionReason: reason.trim() });
    }
  }

  return (
    <article>
      <header className={styles.detailHeader}>
        <div>
          <Badge
            className={`${styles.statusBadge} ${statusClass[invoice.status]}`}
          >
            <span aria-hidden="true" className={styles.statusDot} />
            {invoice.status}
          </Badge>
          <h1>{invoice.invoice_number ?? invoice.filename ?? 'Invoice'}</h1>
          <p className={styles.detailSupplier}>
            {invoice.supplier ??
              (invoice.status === 'Processing'
                ? 'Reading Supplier'
                : 'Supplier not read')}
          </p>
        </div>
        <div className={styles.headerSummary}>
          <div className={styles.total}>
            <p>Invoice total</p>
            <strong aria-label="Invoice total">{money(invoice)}</strong>
          </div>
          {invoice.can_decide && (
            <div className={styles.decisionActions}>
              <Button
                disabled={decision.isPending}
                onClick={() => decision.mutate({ action: 'approve' })}
              >
                {decision.isPending &&
                decision.variables.action === 'approve' ? (
                  <LoaderCircle aria-hidden="true" className={styles.spin} />
                ) : (
                  <Check aria-hidden="true" />
                )}
                Approve
              </Button>
              <Button
                ref={rejectButton}
                variant="outline"
                disabled={decision.isPending}
                onClick={() => {
                  decision.reset();
                  setRejectOpen(true);
                }}
              >
                <X aria-hidden="true" /> Reject
              </Button>
            </div>
          )}
          {role === 'Reviewer' &&
            invoice.status === 'In Review' &&
            invoice.decision_block_reason && (
              <p className={styles.lockNotice}>
                <LockKeyhole aria-hidden="true" size={16} />
                {invoice.decision_block_reason}
              </p>
            )}
        </div>
      </header>

      {rejectOpen && invoice.can_decide && (
        <form
          className={styles.rejectionForm}
          aria-label="Reject Invoice"
          onSubmit={reject}
          aria-busy={decision.isPending}
        >
          <label htmlFor="rejection-reason">Rejection Reason</label>
          <textarea
            ref={reasonInput}
            id="rejection-reason"
            required
            maxLength={2000}
            rows={3}
            value={reason}
            onChange={(event) => setReason(event.currentTarget.value)}
            disabled={decision.isPending}
          />
          <div className={styles.rejectionActions}>
            <Button
              type="button"
              variant="ghost"
              disabled={decision.isPending}
              onClick={() => {
                setRejectOpen(false);
                setReason('');
                decision.reset();
                rejectButton.current?.focus();
              }}
            >
              <X aria-hidden="true" /> Cancel
            </Button>
            <Button
              type="submit"
              variant="destructive"
              disabled={!reason.trim() || decision.isPending}
            >
              {decision.isPending ? (
                <LoaderCircle aria-hidden="true" className={styles.spin} />
              ) : (
                <X aria-hidden="true" />
              )}
              Reject Invoice
            </Button>
          </div>
        </form>
      )}

      {decision.error && (
        <p className={styles.decisionError} role="alert">
          {decision.error instanceof ApiError
            ? decision.error.message
            : 'Unable to save this decision. Please try again.'}
        </p>
      )}

      {invoice.rejection_reason && (
        <section
          className={`${styles.reasons} ${styles.rejectionReason}`}
          aria-label="Rejection Reason"
        >
          <h2>Rejection Reason</h2>
          <p>{invoice.rejection_reason}</p>
        </section>
      )}

      {invoice.steps.length > 0 && (
        <section className={styles.pipeline} aria-label="Agent progress">
          <h2>Agent steps</h2>
          <ol aria-label="Agent steps">
            {invoice.steps.map((step) => {
              const Icon =
                step.status === 'Completed'
                  ? Check
                  : step.status === 'Failed'
                    ? TriangleAlert
                    : step.status === 'Running'
                      ? LoaderCircle
                      : step.status === 'Skipped'
                        ? CircleMinus
                        : Circle;
              const supplier =
                step.name === 'Find Supplier' ? step.outputs?.supplier : null;
              const supplierName =
                supplier &&
                typeof supplier === 'object' &&
                !Array.isArray(supplier) &&
                typeof supplier.name === 'string'
                  ? supplier.name
                  : null;
              return (
                <li key={step.name} data-status={step.status}>
                  <Icon
                    aria-hidden="true"
                    size={18}
                    className={
                      step.status === 'Running' ? styles.spin : undefined
                    }
                  />
                  <div>
                    <strong>{step.name}</strong>
                    <span>{step.status}</span>
                    {supplierName && <span>{supplierName}</span>}
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      )}

      <dl className={styles.metadata}>
        <div>
          <dt>Invoice date</dt>
          <dd>
            {invoice.issued_on ? (
              <time dateTime={invoice.issued_on}>
                {new Intl.DateTimeFormat('en-GB', {
                  dateStyle: 'medium',
                  timeZone: 'UTC',
                }).format(new Date(invoice.issued_on))}
              </time>
            ) : (
              '-'
            )}
          </dd>
        </div>
        <div>
          <dt>Currency</dt>
          <dd>{invoice.currency}</dd>
        </div>
      </dl>

      {invoice.fields && (
        <section
          className={
            invoice.comparison.length > 0
              ? styles.comparison
              : styles.readFields
          }
          aria-label={
            invoice.comparison.length > 0 ? 'Three-Way Match' : 'Read fields'
          }
        >
          <h2>
            {invoice.comparison.length > 0 ? 'Three-Way Match' : 'Read fields'}
          </h2>
          {invoice.fields.purchase_order_number && (
            <p className={styles.purchaseOrder}>
              Purchase Order <span>{invoice.fields.purchase_order_number}</span>
            </p>
          )}
          {invoice.comparison.length > 0 ? (
            invoice.comparison.map((line) => (
              <ComparisonLine
                key={line.line_number}
                line={line}
                currency={invoice.currency}
              />
            ))
          ) : (
            <div className={styles.linesScroll}>
              <table>
                <caption className="sr-only">Invoice lines</caption>
                <thead>
                  <tr>
                    <th scope="col">Description</th>
                    <th scope="col">Quantity</th>
                    <th scope="col">Unit price</th>
                  </tr>
                </thead>
                <tbody>
                  {invoice.fields.lines.map((line, index) => (
                    <tr key={index}>
                      <td>{line.description}</td>
                      <td>{line.quantity}</td>
                      <td>
                        {money({
                          total: line.unit_price,
                          currency: invoice.currency,
                        })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <dl className={styles.readTotals}>
            <div>
              <dt>Subtotal</dt>
              <dd>
                {money({
                  total: invoice.fields.subtotal,
                  currency: invoice.currency,
                })}
              </dd>
            </div>
            <div>
              <dt>Tax</dt>
              <dd>
                {money({
                  total: invoice.fields.tax,
                  currency: invoice.currency,
                })}
              </dd>
            </div>
          </dl>
        </section>
      )}

      {invoice.reasons.length > 0 && (
        <section className={styles.reasons} aria-label="Review reasons">
          <h2>Review reasons</h2>
          <ul>
            {invoice.reasons
              .filter(
                (reason) =>
                  !duplicates.some((duplicate) => duplicate.reason === reason),
              )
              .map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            {duplicates.map((duplicate) => (
              <li key={duplicate.invoice_id}>
                <Link
                  href={`?invoice=${duplicate.invoice_id}`}
                  prefetch={false}
                  aria-disabled={decision.isPending}
                  onNavigate={(event) => {
                    event.preventDefault();
                    if (!decision.isPending)
                      onOpenInvoice(duplicate.invoice_id);
                  }}
                >
                  {duplicate.reason}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <dl className={styles.recordId}>
        <dt>Record ID</dt>
        <dd>{invoice.id}</dd>
      </dl>
    </article>
  );
}
