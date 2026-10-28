'use client';

import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import {
  skipToken,
  useIsMutating,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
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
  demoRoles,
  getInvoice,
  getInvoiceCounts,
  listInvoices,
  money,
  type DemoRole,
  type InvoiceDetail,
  type InvoiceHeader,
  type InvoiceView,
} from './api';
import { InvoiceDetails, statusClass } from './invoice-details';
import { UploadInvoice } from './upload-invoice';
import styles from './split-view.module.css';

const views = [
  { id: 'all', label: 'All', count: 'all' },
  { id: 'mine', label: 'Mine', count: 'mine' },
  { id: 'review-queue', label: 'Review Queue', count: 'review_queue' },
  { id: 'done', label: 'Done', count: 'done' },
] as const;

const defaultViews: Record<DemoRole, InvoiceView> = {
  Submitter: 'mine',
  Reviewer: 'review-queue',
  Admin: 'all',
};

function errorMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : 'Unable to reach the Invoice service.';
}

export function SplitView() {
  const queryClient = useQueryClient();
  const busy = useIsMutating() > 0;
  const main = useRef<HTMLElement>(null);
  const [role, setRole] = useState<DemoRole>('Submitter');
  const [view, setView] = useState<InvoiceView>('mine');
  const [chosenId, setChosenId] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [sessionError, setSessionError] =
    useState<DemoCompanyExpiredError | null>(null);

  const demoCompany = useQuery({
    queryKey: ['demo-company'],
    queryFn: startDemoCompany,
    staleTime: Infinity,
  });
  const companyId = demoCompany.data?.id;
  const invoiceCounts = useQuery({
    queryKey: ['invoices', companyId, 'counts', role],
    queryFn: ({ signal }) => getInvoiceCounts(signal, role),
    enabled: companyId !== undefined,
    refetchInterval: (query) => {
      const counts = query.state.data;
      return counts && counts.all > counts.review_queue + counts.done
        ? 1000
        : false;
    },
  });
  const invoiceList = useQuery({
    queryKey: ['invoices', companyId, 'list', role, view],
    queryFn: ({ signal }) => listInvoices(signal, role, view),
    enabled: companyId !== undefined,
    refetchInterval: (query) =>
      query.state.data?.some((invoice) => invoice.status === 'Processing')
        ? 1000
        : false,
  });

  useEffect(() => {
    if (companyId && invoiceCounts.data) {
      void queryClient.invalidateQueries({
        queryKey: ['invoices', companyId, 'list'],
      });
    }
  }, [companyId, invoiceCounts.data, queryClient]);

  const invoices = invoiceList.isSuccess ? invoiceList.data : [];
  const company = invoiceList.isSuccess ? demoCompany.data : undefined;
  const selectedId = chosenId ?? invoices[0]?.id ?? null;

  const invoice = useQuery({
    queryKey: ['invoices', companyId, 'detail', role, selectedId],
    queryFn:
      selectedId === null
        ? skipToken
        : ({ signal }) => getInvoice(selectedId, signal, role),
    enabled: !uploadOpen,
    refetchInterval: (query) =>
      query.state.data?.status === 'Processing' ||
      query.state.data?.steps.some((step) =>
        ['Pending', 'Running'].includes(step.status),
      )
        ? 1000
        : false,
  });
  const selected =
    invoices.find((header) => header.id === selectedId) ?? invoice.data;

  const error =
    demoCompany.error ??
    invoiceList.error ??
    invoiceCounts.error ??
    invoice.error ??
    sessionError;
  const loading =
    !demoCompany.isError && (invoiceList.isPending || invoiceCounts.isPending);

  function changeView(nextView: InvoiceView) {
    setView(nextView);
    setChosenId(null);
    setUploadOpen(false);
    main.current?.scrollTo({ top: 0 });
  }

  function changeRole(nextRole: DemoRole) {
    setRole(nextRole);
    changeView(defaultViews[nextRole]);
  }

  function navigateTabs(event: KeyboardEvent<HTMLDivElement>) {
    if (busy) return;
    const index = views.findIndex((tab) => tab.id === view);
    const nextIndex =
      event.key === 'ArrowRight'
        ? (index + 1) % views.length
        : event.key === 'ArrowLeft'
          ? (index + views.length - 1) % views.length
          : event.key === 'Home'
            ? 0
            : event.key === 'End'
              ? views.length - 1
              : null;
    if (nextIndex === null) return;
    event.preventDefault();
    const nextView = views[nextIndex].id;
    changeView(nextView);
    event.currentTarget
      .querySelector<HTMLButtonElement>(`#invoice-view-${nextView}`)
      ?.focus();
  }

  function refresh() {
    void queryClient.resetQueries({
      queryKey: demoCompany.isError ? ['demo-company'] : ['invoices'],
    });
  }

  function startNewDemoCompany() {
    setSessionError(null);
    setUploadOpen(false);
    setChosenId(null);
    setView(defaultViews[role]);
    void queryClient.resetQueries({ queryKey: ['demo-company'] });
  }

  function uploaded(invoice: InvoiceDetail) {
    queryClient.setQueryData(
      ['invoices', companyId, 'detail', role, invoice.id],
      invoice,
    );
    queryClient.setQueryData<InvoiceHeader[]>(
      ['invoices', companyId, 'list', role, 'mine'],
      (current) => [
        invoice,
        ...(current ?? []).filter((existing) => existing.id !== invoice.id),
      ],
    );
    setView('mine');
    setChosenId(invoice.id);
    setUploadOpen(false);
    main.current?.scrollTo({ top: 0 });
    void queryClient.invalidateQueries({ queryKey: ['invoices', companyId] });
  }

  function decided(invoice: InvoiceDetail) {
    queryClient.setQueryData(
      ['invoices', companyId, 'detail', role, invoice.id],
      invoice,
    );
    setChosenId(invoice.id);
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
        key={`${companyId}:${role}`}
        role={role}
        onUploaded={uploaded}
        onCancel={() => setUploadOpen(false)}
        onExpired={setSessionError}
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
    content = (
      <InvoiceDetails
        key={`${role}:${invoice.data.id}`}
        invoice={invoice.data}
        role={role}
        onDecided={decided}
        onExpired={setSessionError}
      />
    );
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

        <div className={styles.sidebarControls}>
          <div className={styles.roleSwitch}>
            <label htmlFor="viewing-as">Viewing as</label>
            <select
              id="viewing-as"
              value={role}
              onChange={(event) =>
                changeRole(event.currentTarget.value as DemoRole)
              }
              disabled={busy}
            >
              {demoRoles.map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>
          </div>
          <div className={styles.uploadAction}>
            <Button
              className={styles.uploadButton}
              onClick={() => {
                setUploadOpen(true);
                main.current?.scrollTo({ top: 0 });
              }}
              disabled={loading || Boolean(error) || busy}
              aria-pressed={uploadOpen}
            >
              <Upload aria-hidden="true" /> Upload Invoice
            </Button>
          </div>
        </div>

        <div
          className={styles.viewTabs}
          role="tablist"
          aria-label="Invoice views"
          onKeyDown={navigateTabs}
        >
          {views.map((tab) => (
            <button
              key={tab.id}
              id={`invoice-view-${tab.id}`}
              type="button"
              role="tab"
              aria-selected={view === tab.id}
              aria-controls="invoice-list"
              tabIndex={view === tab.id ? 0 : -1}
              className={styles.viewTab}
              onClick={() => changeView(tab.id)}
              disabled={busy}
            >
              {tab.label}{' '}
              <span className={styles.tabCount}>
                {invoiceCounts.data?.[tab.count] ?? '-'}
              </span>
            </button>
          ))}
        </div>

        <nav className={styles.invoiceList} aria-label="Invoice list">
          <div
            id="invoice-list"
            role="tabpanel"
            aria-labelledby={`invoice-view-${view}`}
            tabIndex={0}
          >
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
                      disabled={busy}
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
                        <span className={styles.listTotal}>
                          {money(invoice)}
                        </span>
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
            {!loading && invoices.length === 0 && (
              <p className={styles.emptyList}>No Invoices</p>
            )}
          </div>
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
