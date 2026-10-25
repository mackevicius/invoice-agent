"use client";
// PROTOTYPE: in-memory demo state shared by all variants. No persistence.

import { useCallback, useReducer } from "react";
import {
  type AgentResult,
  type CaseKey,
  type Invoice,
  caseOrder,
  DEFAULT_LIMIT,
  runAgent,
  sampleCases,
} from "./demo-data";

export type Role = "Submitter" | "Reviewer" | "Admin";
export const roles: Role[] = ["Submitter", "Reviewer", "Admin"];
export const YOU = "You";

export type Status = "running" | "auto-approved" | "in-review" | "approved" | "rejected";

export const statusLabel: Record<Status, string> = {
  running: "Agent working",
  "auto-approved": "Auto-Approved",
  "in-review": "In Review Queue",
  approved: "Approved",
  rejected: "Rejected",
};

export type InvoiceRecord = {
  id: string;
  caseKey: CaseKey;
  fileName: string;
  invoice: Invoice;
  result: AgentResult;
  submittedBy: string;
  submittedAt: string;
  stepsShown: number;
  status: Status;
  decidedBy: string | null;
};

type State = { role: Role; limit: number; records: InvoiceRecord[]; uploads: number };

type Action =
  | { type: "role"; role: Role }
  | { type: "limit"; limit: number }
  | { type: "add"; record: InvoiceRecord }
  | { type: "reveal"; id: string }
  | { type: "decide"; id: string; status: "approved" | "rejected" };

const STEP_MS = 800;

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "role":
      return { ...state, role: action.role };
    case "limit":
      return { ...state, limit: action.limit };
    case "add":
      return { ...state, records: [action.record, ...state.records], uploads: state.uploads + 1 };
    case "reveal":
      return {
        ...state,
        records: state.records.map((r) => {
          if (r.id !== action.id) return r;
          const stepsShown = r.stepsShown + 1;
          const done = stepsShown >= r.result.steps.length;
          const status: Status = !done
            ? "running"
            : r.result.decision === "auto-approve"
              ? "auto-approved"
              : "in-review";
          return { ...r, stepsShown, status, decidedBy: done && status === "auto-approved" ? "Agent" : null };
        }),
      };
    case "decide":
      return {
        ...state,
        records: state.records.map((r) =>
          r.id === action.id ? { ...r, status: action.status, decidedBy: YOU } : r,
        ),
      };
  }
}

const seeds: { caseKey: CaseKey; number: string; by: string; at: string }[] = [
  { caseKey: "duplicate", number: "INV-1042", by: "Dana Kim", at: "Mon 09:14" },
  { caseKey: "price", number: "INV-2219", by: "Dana Kim", at: "Tue 11:02" },
  { caseKey: "over-limit", number: "INV-2236", by: "Marek Ozols", at: "Wed 08:47" },
  { caseKey: "unknown-supplier", number: "INV-71", by: "Dana Kim", at: "Wed 14:20" },
  { caseKey: "quantity", number: "INV-3301", by: YOU, at: "Today 08:05" },
];

function initialState(): State {
  const records: InvoiceRecord[] = [];
  seeds.forEach((s, i) => {
    const invoice = { ...sampleCases[s.caseKey].invoice, number: s.number };
    const prior = records.map((r) => ({ ...r.invoice, submittedAt: r.submittedAt }));
    const result = runAgent(invoice, prior, DEFAULT_LIMIT);
    records.unshift({
      id: `seed-${i}`,
      caseKey: s.caseKey,
      fileName: `${s.number}.pdf`,
      invoice,
      result,
      submittedBy: s.by,
      submittedAt: s.at,
      stepsShown: result.steps.length,
      status: result.decision === "auto-approve" ? "auto-approved" : "in-review",
      decidedBy: result.decision === "auto-approve" ? "Agent" : null,
    });
  });
  return { role: "Submitter", limit: DEFAULT_LIMIT, records, uploads: 0 };
}

export function useInvoiceDemo() {
  const [state, dispatch] = useReducer(reducer, undefined, initialState);

  const upload = useCallback(
    (caseKey?: CaseKey, fileName?: string) => {
      const key = caseKey ?? caseOrder[state.uploads % caseOrder.length];
      const invoice = sampleCases[key].invoice;
      const prior = state.records.map((r) => ({ ...r.invoice, submittedAt: r.submittedAt }));
      const result = runAgent(invoice, prior, state.limit);
      const id = `up-${Date.now()}`;
      dispatch({
        type: "add",
        record: {
          id,
          caseKey: key,
          fileName: fileName ?? `${invoice.number}.pdf`,
          invoice,
          result,
          submittedBy: YOU,
          submittedAt: `Today ${new Date().toTimeString().slice(0, 5)}`,
          stepsShown: 0,
          status: "running",
          decidedBy: null,
        },
      });
      for (let i = 1; i <= result.steps.length; i++) {
        setTimeout(() => dispatch({ type: "reveal", id }), i * STEP_MS);
      }
      return id;
    },
    [state.uploads, state.records, state.limit],
  );

  return {
    ...state,
    reviewQueue: state.records.filter((r) => r.status === "in-review"),
    setRole: (role: Role) => dispatch({ type: "role", role }),
    setLimit: (limit: number) => dispatch({ type: "limit", limit }),
    upload,
    approve: (id: string) => dispatch({ type: "decide", id, status: "approved" }),
    reject: (id: string) => dispatch({ type: "decide", id, status: "rejected" }),
  };
}

export type Demo = ReturnType<typeof useInvoiceDemo>;

export function canDecide(record: InvoiceRecord, role: Role): { ok: boolean; why: string | null } {
  if (role !== "Reviewer") return { ok: false, why: "Only a Reviewer can approve or reject." };
  if (record.status !== "in-review") return { ok: false, why: null };
  if (record.submittedBy === YOU)
    return { ok: false, why: "You submitted this Invoice, so another Reviewer must decide it." };
  return { ok: true, why: null };
}

// Fake Langfuse link for the prototype.
export const traceHref = (id: string) => `#langfuse-trace-${id}`;
