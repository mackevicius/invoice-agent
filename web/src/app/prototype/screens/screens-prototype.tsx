"use client";

import { useSearchParams } from "next/navigation";
import { PrototypeSwitcher } from "@/components/prototype-switcher";
import { useInvoiceDemo } from "./use-demo";
import { name as nameA, VariantA } from "./variant-a";
import { name as nameB, VariantB } from "./variant-b";
import { name as nameC, VariantC } from "./variant-c";

const variants = [
  { key: "A", name: nameA },
  { key: "B", name: nameB },
  { key: "C", name: nameC },
];

export function ScreensPrototype() {
  const demo = useInvoiceDemo();
  const variant = useSearchParams().get("variant") ?? "A";

  return (
    <>
      {variant === "A" && <VariantA demo={demo} />}
      {variant === "B" && <VariantB demo={demo} />}
      {variant === "C" && <VariantC demo={demo} />}
      <PrototypeSwitcher variants={variants} />
    </>
  );
}
