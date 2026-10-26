'use client';

import { useRef, useState, type ReactNode } from 'react';
import { skipToken, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ChevronRight,
  Clock3,
  FileText,
  ReceiptText,
  RotateCw,
  TriangleAlert,
  Upload,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { startDemoCompany } from '@/features/demo-company/api';
import { ApiError, DemoCompanyExpiredError } from '@/lib/api';
import {
  getInvoice,
  listInvoices,
  money,
  type InvoiceDetail,
  type InvoiceHeader,
} from './api';
import { InvoiceDetails, statusClass } from './invoice-details';
import { UploadInvoice } from './upload-invoice';
import styles from './split-view.module.css';

function errorMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : 'Unable to reach the Invoice service.';
}

export function SplitView() {
  const queryClient = useQueryClient();
  const main = useRef<HTMLElement>(null);
  const [chosenId, setChosenId] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadSessionError, setUploadSessionError] =
    useState<DemoCompanyExpiredError | null>(null);

  const demoCompany = useQuery({
    queryKey: ['demo-company'],
    queryFn: startDemoCompany,
    staleTime: Infinity,
  });
  const companyId = demoCompany.data?.id;
  const invoiceList = useQuery({
    queryKey: ['invoices', companyId],
    queryFn: ({ signal }) => listInvoices(signal),
    enabled: companyId !== undefined,
    refetchInterval: (query) =>
      query.state.data?.some((invoice) => invoice.status === 'Processing')
        ? 1000
        : false,
  });

  const invoices = invoiceList.isSuccess ? invoiceList.data : [];
  const company = invoiceList.isSuccess ? demoCompany.data : undefined;
  const selected =
    invoices.find((invoice) => invoice.id === chosenId) ?? invoices[0];
  const selectedId = selected?.id ?? null;

  const invoice = useQuery({
    queryKey: ['invoices', companyId, selectedId],
    queryFn:
      selectedId === null
        ? skipToken
        : ({ signal }) => getInvoice(selectedId, signal),
    enabled: !uploadOpen,
    refetchInterval: (query) =>
      query.state.data?.status === 'Processing' ? 1000 : false,
  });

  const error =
    demoCompany.error ??
    invoiceList.error ??
    invoice.error ??
    uploadSessionError;
  const loading = !demoCompany.isError && invoiceList.isPending;

  function refresh() {
    void queryClient.resetQueries({
      queryKey: demoCompany.isError ? ['demo-company'] : ['invoices'],
    });
  }

  function startNewDemoCompany() {
    setUploadSessionError(null);
    setUploadOpen(false);
    void queryClient.resetQueries({ queryKey: ['demo-company'] });
  }

  function uploaded(invoice: InvoiceDetail) {
    queryClient.setQueryData(['invoices', companyId, invoice.id], invoice);
    queryClient.setQueryData<InvoiceHeader[]>(
      ['invoices', companyId],
      (current) => [
        invoice,
        ...(current ?? []).filter((existing) => existing.id !== invoice.id),
      ],
    );
    setChosenId(invoice.id);
    setUploadOpen(false);
    main.current?.scrollTo({ top: 0 });
  }

  let content: ReactNode;
  if (error instanceof DemoCompanyExpiredError) {
    content = (
      <ErrorState title="Demo Company expired" message={error.message}>
        <Button variant="outline" onClick={startNewDemoCompany}>
          Start a new Demo Company
        </Button>
      </ErrorState>
    );
  } else if (error) {
    content = (
      <ErrorState title="Invoices unavailable" message={errorMessage(error)}>
        <Button variant="outline" onClick={refresh}>
          <RotateCw aria-hidden="true" /> Retry
        </Button>
      </ErrorState>
    );
  } else if (loading) {
    content = <LoadingInvoice />;
  } else if (uploadOpen) {
    content = (
      <UploadInvoice
        key={companyId}
        onUploaded={uploaded}
        onCancel={() => setUploadOpen(false)}
        onExpired={setUploadSessionError}
      />
    );
  } else if (selectedId === null) {
    content = (
      <div className={styles.empty}>
        <ReceiptText aria-hidden="true" size={28} />
        <h1>No Invoices</h1>
      </div>
    );
  } else if (invoice.isSuccess) {
    content = <InvoiceDetails invoice={invoice.data} />;
  } else {
    content = <LoadingInvoice />;
  }

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar} aria-label="Invoices">
        <header className={styles.brand}>
          <span className={styles.brandMark}>
            <ReceiptText aria-hidden="true" size={21} />
          </span>
          <div>
            <p className={styles.brandName}>Invoice Agent</p>
            <p className={styles.companyLabel}>
              Demo Company
              {company && <span>{company.id.slice(0, 8)}</span>}
            </p>
          </div>
        </header>

        <div className={styles.uploadAction}>
          <Button
            className={styles.uploadButton}
            onClick={() => {
              setUploadOpen(true);
              main.current?.scrollTo({ top: 0 });
            }}
            disabled={loading || Boolean(error)}
            aria-pressed={uploadOpen}
          >
            <Upload aria-hidden="true" /> Upload Invoice
          </Button>
        </div>

        <div className={styles.listHeading}>
          <h2>Invoices</h2>
          <span className={styles.count}>
            {invoiceList.isSuccess ? invoices.length : '-'}
          </span>
        </div>

        <nav className={styles.invoiceList} aria-label="Invoice list">
          {loading ? (
            <ul aria-label="Loading Invoices" aria-busy="true">
              {Array.from({ length: 5 }, (_, index) => (
                <li className={styles.loadingRow} key={index}>
                  <Skeleton className="h-3 w-24 bg-white/10" />
                  <Skeleton className="mt-3 h-3 w-40 bg-white/10" />
                </li>
              ))}
            </ul>
          ) : (
            <ul>
              {invoices.map((invoice) => (
                <li key={invoice.id}>
                  <button
                    type="button"
                    className={styles.invoiceButton}
                    aria-pressed={!uploadOpen && selectedId === invoice.id}
                    onClick={() => {
                      setChosenId(invoice.id);
                      setUploadOpen(false);
                      main.current?.scrollTo({ top: 0 });
                    }}
                  >
                    <span className={styles.invoiceRow}>
                      <span className={styles.invoiceIdentity}>
                        <span
                          aria-hidden="true"
                          className={`${styles.statusDot} ${statusClass[invoice.status]}`}
                        />
                        <span className={styles.invoiceNumber}>
                          {invoice.invoice_number ?? 'Reading Invoice'}
                        </span>
                      </span>
                      <span className={styles.listTotal}>{money(invoice)}</span>
                    </span>
                    <span
                      className={styles.supplierName}
                      title={invoice.supplier ?? undefined}
                    >
                      {invoice.supplier ?? invoice.status}
                    </span>
                    <span className="sr-only">{invoice.status}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </nav>

        <footer className={styles.companyFooter}>
          <Clock3 aria-hidden="true" size={14} />
          {company ? (
            <span>
              Expires{' '}
              <time dateTime={company.expires_at}>
                {new Intl.DateTimeFormat('en-GB', {
                  day: 'numeric',
                  month: 'short',
                  hour: '2-digit',
                  minute: '2-digit',
                }).format(new Date(company.expires_at))}
              </time>
            </span>
          ) : (
            <span>Demo Company</span>
          )}
        </footer>
      </aside>

      <main ref={main} className={styles.main} aria-label="Invoice details">
        <div className={styles.toolbar}>
          <div className={styles.breadcrumb}>
            <FileText aria-hidden="true" size={15} />
            <span>Invoices</span>
            {uploadOpen ? (
              <>
                <ChevronRight aria-hidden="true" size={14} />
                <span>Upload Invoice</span>
              </>
            ) : (
              selected && (
                <>
                  <ChevronRight aria-hidden="true" size={14} />
                  <span className={styles.breadcrumbNumber}>
                    {selected.invoice_number ?? 'Reading Invoice'}
                  </span>
                </>
              )
            )}
          </div>
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Refresh Invoices"
                  onClick={refresh}
                  disabled={loading}
                />
              }
            >
              <RotateCw aria-hidden="true" size={16} />
            </TooltipTrigger>
            <TooltipContent>Refresh Invoices</TooltipContent>
          </Tooltip>
        </div>
        <div aria-live="polite">{content}</div>
      </main>
    </div>
  );
}

function LoadingInvoice() {
  return (
    <div
      className={styles.loadingDetail}
      role="status"
      aria-label="Loading Invoice"
    >
      <Skeleton className="h-5 w-28" />
      <Skeleton className="mt-5 h-9 w-48" />
      <Skeleton className="mt-3 h-4 w-60 max-w-full" />
      <div className="mt-12 grid grid-cols-2 gap-6">
        <Skeleton className="h-12 w-28 max-w-full" />
        <Skeleton className="h-12 w-20 max-w-full" />
      </div>
      <span className="sr-only">Loading Invoice</span>
    </div>
  );
}

function ErrorState({
  title,
  message,
  children,
}: {
  title: string;
  message: string;
  children: ReactNode;
}) {
  return (
    <div className={styles.error} role="alert">
      <TriangleAlert aria-hidden="true" size={24} />
      <h1>{title}</h1>
      <p>{message}</p>
      {children}
    </div>
  );
}
