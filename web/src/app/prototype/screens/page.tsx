// PROTOTYPE route: /prototype/screens?variant=A|B|C
// Question: what should the Invoice Agent screens (Upload, live agent steps, Review Queue, Admin) look like?
// Three structurally different variants on one route, fake in-memory data, no backend.

import { Suspense } from "react";
import { ScreensPrototype } from "./screens-prototype";

export default function Page() {
  return (
    <Suspense>
      <ScreensPrototype />
    </Suspense>
  );
}
