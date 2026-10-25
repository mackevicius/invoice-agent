"use client";
// PROTOTYPE tool: floating bar to flip between UI variants via ?variant=. Hidden in production.

import { useCallback, useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

export function PrototypeSwitcher({ variants }: { variants: { key: string; name: string }[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const current = params.get("variant") ?? variants[0].key;
  const index = Math.max(0, variants.findIndex((v) => v.key === current));

  const go = useCallback(
    (delta: number) => {
      const next = variants[(index + delta + variants.length) % variants.length];
      const p = new URLSearchParams(params.toString());
      p.set("variant", next.key);
      router.replace(`${pathname}?${p}`, { scroll: false });
    },
    [index, variants, params, pathname, router],
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      if (t?.closest("input, textarea, select, [contenteditable]") || t?.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "ArrowLeft") go(-1);
      if (e.key === "ArrowRight") go(1);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

  if (process.env.NODE_ENV === "production") return null;

  const v = variants[index];
  return (
    <div className="fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-1 rounded-full bg-black px-2 py-1.5 font-mono text-sm text-white shadow-2xl ring-2 ring-fuchsia-500">
      <button onClick={() => go(-1)} className="rounded-full px-2 hover:bg-white/20" aria-label="Previous variant">
        ←
      </button>
      <span className="min-w-56 text-center">
        PROTOTYPE {v.key} ({v.name})
      </span>
      <button onClick={() => go(1)} className="rounded-full px-2 hover:bg-white/20" aria-label="Next variant">
        →
      </button>
    </div>
  );
}
