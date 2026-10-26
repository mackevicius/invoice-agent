import { Check, Circle, LoaderCircle, TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { money, type InvoiceDetail } from './api';
import styles from './split-view.module.css';

export const statusClass: Record<InvoiceDetail['status'], string> = {
  Processing: styles.processing,
  'In Review': styles.review,
  'Auto-Approved': styles.autoApproved,
  Approved: styles.approved,
  Rejected: styles.rejected,
};

export function InvoiceDetails({ invoice }: { invoice: InvoiceDetail }) {
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
        <div className={styles.total}>
          <p>Invoice total</p>
          <strong aria-label="Invoice total">{money(invoice)}</strong>
        </div>
      </header>

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
                      : Circle;
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
        <section className={styles.readFields} aria-label="Read fields">
          <h2>Read fields</h2>
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
            {invoice.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
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
