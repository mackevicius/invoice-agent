"use client";
// PROTOTYPE: tiny bits shared by all variants. Layout stays inside each variant.

import { CircleAlert, CircleCheck, CircleMinus, CircleX, LoaderCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { StepStatus } from "./demo-data";
import { type Status, statusLabel } from "./use-demo";

export function StepIcon({ status, className = "size-4" }: { status: StepStatus | "pending"; className?: string }) {
  if (status === "pending") return <LoaderCircle className={`${className} animate-spin text-muted-foreground`} />;
  if (status === "ok") return <CircleCheck className={`${className} text-emerald-600`} />;
  if (status === "warn") return <CircleAlert className={`${className} text-amber-600`} />;
  if (status === "fail") return <CircleX className={`${className} text-red-600`} />;
  return <CircleMinus className={`${className} text-muted-foreground`} />;
}

const statusClass: Record<Status, string> = {
  running: "bg-sky-100 text-sky-800",
  "auto-approved": "bg-emerald-100 text-emerald-800",
  "in-review": "bg-amber-100 text-amber-900",
  approved: "bg-emerald-600 text-white",
  rejected: "bg-red-600 text-white",
};

export function StatusBadge({ status }: { status: Status }) {
  return <Badge className={statusClass[status]}>{statusLabel[status]}</Badge>;
}

export const demoCompanyNote = "Demo Company · your private copy, wiped in 23 h 52 min";
