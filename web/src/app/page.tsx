import { Suspense } from 'react';
import { SplitView } from '@/features/invoices/split-view';

export default function Home() {
  return (
    <Suspense>
      <SplitView />
    </Suspense>
  );
}
