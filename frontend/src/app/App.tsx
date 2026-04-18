import { useState } from "react";

import type { DetectionResponse } from "../features/detection/types";
import { DetectorPage } from "../pages/DetectorPage";
import { ReportsPage } from "../pages/ReportsPage";
import { PageShell } from "../shared/components/PageShell";

export function App() {
  const [result, setResult] = useState<DetectionResponse | null>(null);

  return (
    <PageShell>
      <DetectorPage onCompleted={setResult} />
      <ReportsPage result={result} />
    </PageShell>
  );
}
