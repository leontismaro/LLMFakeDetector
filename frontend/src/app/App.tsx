import { useState } from "react";

import { MOCK_DETECTION_RESPONSE, MOCK_RUN_SUMMARY } from "../features/detection/mockReport";
import type { DetectionResponse, DetectionRunSummary } from "../features/detection/types";
import { DetectorPage } from "../pages/DetectorPage";
import { ReportsPage } from "../pages/ReportsPage";
import { PageShell } from "../shared/components/PageShell";

export function App() {
  const [result, setResult] = useState<DetectionResponse | null>(null);
  const [runSummary, setRunSummary] = useState<DetectionRunSummary | null>(null);
  const [isDetectorCollapsed, setIsDetectorCollapsed] = useState(false);
  const [isRunning, setIsRunning] = useState(false);

  function handleLoadMock() {
    setRunSummary(MOCK_RUN_SUMMARY);
    setResult(MOCK_DETECTION_RESPONSE);
    setIsRunning(false);
    setIsDetectorCollapsed(true);
  }

  return (
    <PageShell isDetectorCollapsed={isDetectorCollapsed}>
      <DetectorPage
        result={result}
        runSummary={runSummary}
        isCollapsed={isDetectorCollapsed}
        isRunning={isRunning}
        onCollapseChange={setIsDetectorCollapsed}
        onSubmittingChange={setIsRunning}
        onCompleted={setResult}
        onRunStart={setRunSummary}
        onLoadMock={handleLoadMock}
      />
      <ReportsPage result={result} runSummary={runSummary} />
    </PageShell>
  );
}
