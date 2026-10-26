"use client";

import { useEffect, useState, type ReactNode } from "react";
import {
  ChevronRight,
  Clock3,
  FileText,
  ReceiptText,
  RotateCw,
  TriangleAlert,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  ApiError,
  getInvoice,
  loadWorkspace,
  type InvoiceHeader,
  type Workspace,
} from "./api";
import styles from "./split-view.module.css";

type WorkspaceState =
  | { status: "loading" }
  | { status: "ready"; data: Workspace }
  | { status: "error"; message: string };

type DetailState = { id: string; revision: number } & (
  | { status: "ready"; invoice: InvoiceHeader }
  | { status: "error"; message: string }
);

const statusClass: Record<InvoiceHeader["status"], string> = {
  Processing: styles.processing,
  "In Review": styles.review,
  "Auto-Approved": styles.autoApproved,
  Approved: styles.approved,
  Rejected: styles.rejected,
};

function money(invoice: InvoiceHeader): string {
  return new Intl.NumberFormat("en-IE", {
    style: "currency",
    currency: invoice.currency,
  }).format(Number(invoice.total));
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "Unable to reach the Invoice service.";
}

export function SplitView() {
  const [workspace, setWorkspace] = useState<WorkspaceState>({ status: "loading" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DetailState | null>(null);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    loadWorkspace()
      .then((data) => {
        if (!active) return;
        setWorkspace({ status: "ready", data });
        setSelectedId((previous) =>
          data.invoices.some((invoice) => invoice.id === previous)
            ? previous
            : (data.invoices[0]?.id ?? null),
        );
      })
      .catch((error: unknown) => {
        if (active) setWorkspace({ status: "error", message: errorMessage(error) });
      });
    return () => {
      active = false;
    };
  }, [revision]);

  useEffect(() => {
    if (selectedId === null) return;
    const controller = new AbortController();
    getInvoice(selectedId, controller.signal)
      .then((invoice) => {
        if (!controller.signal.aborted) {
          setDetail({ status: "ready", id: selectedId, revision, invoice });
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setDetail({
            status: "error", id: selectedId, revision,
            message: errorMessage(error),
          });
        }
      });
    return () => controller.abort();
  }, [selectedId, revision]);

  const invoices = workspace.status === "ready" ? workspace.data.invoices : [];
  const company = workspace.status === "ready" ? workspace.data.company : null;
  const selected = invoices.find((invoice) => invoice.id === selectedId);
  const currentDetail =
    detail?.id === selectedId && detail.revision === revision ? detail : null;

  function refresh() {
    setWorkspace({ status: "loading" });
    setRevision((previous) => previous + 1);
  }

  let content: ReactNode;
  if (workspace.status === "error") {
    content = <ErrorState message={workspace.message} onRetry={refresh} />;
  } else if (workspace.status === "loading") {
    content = <LoadingInvoice />;
  } else if (selectedId === null) {
    content = (
      <div className={styles.empty}>
        <ReceiptText aria-hidden="true" size={28} />
        <h1>No Invoices</h1>
      </div>
    );
  } else if (currentDetail?.status === "error") {
    content = <ErrorState message={currentDetail.message} onRetry={refresh} />;
  } else if (currentDetail?.status === "ready") {
    content = <InvoiceDetails invoice={currentDetail.invoice} />;
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

        <div className={styles.listHeading}>
          <h2>Invoices</h2>
          <span className={styles.count}>
            {workspace.status === "ready" ? invoices.length : "-"}
          </span>
        </div>

        <nav className={styles.invoiceList} aria-label="Invoice list">
          {workspace.status === "loading" ? (
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
                    aria-pressed={selectedId === invoice.id}
                    onClick={() => setSelectedId(invoice.id)}
                  >
                    <span className={styles.invoiceRow}>
                      <span className={styles.invoiceIdentity}>
                        <span
                          aria-hidden="true"
                          className={`${styles.statusDot} ${statusClass[invoice.status]}`}
                        />
                        <span className={styles.invoiceNumber}>
                          {invoice.invoice_number}
                        </span>
                      </span>
                      <span className={styles.listTotal}>{money(invoice)}</span>
                    </span>
                    <span className={styles.supplierName} title={invoice.supplier}>
                      {invoice.supplier}
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
              Expires{" "}
              <time dateTime={company.expires_at}>
                {new Intl.DateTimeFormat("en-GB", {
                  day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
                }).format(new Date(company.expires_at))}
              </time>
            </span>
          ) : (
            <span>Demo Company</span>
          )}
        </footer>
      </aside>

      <main className={styles.main} aria-label="Invoice details">
        <div className={styles.toolbar}>
          <div className={styles.breadcrumb}>
            <FileText aria-hidden="true" size={15} />
            <span>Invoices</span>
            {selected && (
              <>
                <ChevronRight aria-hidden="true" size={14} />
                <span className={styles.breadcrumbNumber}>
                  {selected.invoice_number}
                </span>
              </>
            )}
          </div>
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="ghost" size="icon" aria-label="Refresh Invoices"
                  onClick={refresh} disabled={workspace.status === "loading"}
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

function InvoiceDetails({ invoice }: { invoice: InvoiceHeader }) {
  return (
    <article>
      <header className={styles.detailHeader}>
        <div>
          <Badge className={`${styles.statusBadge} ${statusClass[invoice.status]}`}>
            <span aria-hidden="true" className={styles.statusDot} />
            {invoice.status}
          </Badge>
          <h1>{invoice.invoice_number}</h1>
          <p className={styles.detailSupplier}>{invoice.supplier}</p>
        </div>
        <div className={styles.total}>
          <p>Invoice total</p>
          <strong aria-label="Invoice total">{money(invoice)}</strong>
        </div>
      </header>

      <dl className={styles.metadata}>
        <div>
          <dt>Invoice date</dt>
          <dd>
            <time dateTime={invoice.issued_on}>
              {new Intl.DateTimeFormat("en-GB", {
                dateStyle: "medium", timeZone: "UTC",
              }).format(new Date(invoice.issued_on))}
            </time>
          </dd>
        </div>
        <div>
          <dt>Currency</dt>
          <dd>{invoice.currency}</dd>
        </div>
      </dl>
      <dl className={styles.recordId}>
        <dt>Record ID</dt>
        <dd>{invoice.id}</dd>
      </dl>
    </article>
  );
}

function LoadingInvoice() {
  return (
    <div className={styles.loadingDetail} role="status" aria-label="Loading Invoice">
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
  message, onRetry,
}: {
  message: string; onRetry: () => void;
}) {
  return (
    <div className={styles.error} role="alert">
      <TriangleAlert aria-hidden="true" size={24} />
      <h1>Invoices unavailable</h1>
      <p>{message}</p>
      <Button variant="outline" onClick={onRetry}>
        <RotateCw aria-hidden="true" /> Retry
      </Button>
    </div>
  );
}
