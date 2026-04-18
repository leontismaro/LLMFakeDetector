import { DetectorForm } from "../features/detection/components/DetectorForm";
import type { ContextMode, DetectionResponse, DetectionRunSummary } from "../features/detection/types";

interface DetectorPageProps {
  result: DetectionResponse | null;
  runSummary: DetectionRunSummary | null;
  isCollapsed: boolean;
  isRunning: boolean;
  onCollapseChange: (collapsed: boolean) => void;
  onSubmittingChange: (submitting: boolean) => void;
  onCompleted: (result: DetectionResponse) => void;
  onRunStart: (summary: DetectionRunSummary) => void;
  onLoadMock: () => void;
}

const contextModeLabels: Record<ContextMode, string> = {
  light: "轻量",
  standard: "标准",
  heavy: "重度",
};

function formatBaseUrl(value: string): string {
  try {
    const url = new URL(value);
    return url.host || value;
  } catch {
    return value;
  }
}

export function DetectorPage({
  result,
  runSummary,
  isCollapsed,
  isRunning,
  onCollapseChange,
  onSubmittingChange,
  onCompleted,
  onRunStart,
  onLoadMock,
}: DetectorPageProps) {
  function handleRunStart(summary: DetectionRunSummary) {
    onCollapseChange(true);
    onRunStart(summary);
  }

  const hasResult = result !== null;

  return (
    <section className={`card detector-card${isCollapsed ? " detector-card-collapsed" : ""}`}>
      {isCollapsed ? (
        <button
          className="detector-rail"
          type="button"
          onClick={() => onCollapseChange(false)}
          aria-label="展开检测配置"
        >
          <span className="detector-rail-arrow">›</span>
          <span className="detector-rail-title">检测配置</span>
          <span className="detector-rail-status">{isRunning ? "检测中" : hasResult ? "已完成" : "等待结果"}</span>
          {runSummary ? <span className="detector-rail-model">{runSummary.modelName}</span> : null}
        </button>
      ) : (
        <>
          <div className="detector-header">
            <div>
              <h2>检测入口</h2>
            </div>
            <div className="detector-header-actions">
              <button className="secondary-button" type="button" onClick={onLoadMock} disabled={isRunning}>
                加载示例报告
              </button>
              {runSummary ? (
                <button className="secondary-button" type="button" onClick={() => onCollapseChange(true)}>
                  收起面板
                </button>
              ) : null}
            </div>
          </div>

          {runSummary ? (
            <div className="detector-summary">
              <div className="summary-grid compact-grid">
                <div className="summary-item">
                  <div className="summary-label">目标地址</div>
                  <div className="summary-value summary-value-small">{formatBaseUrl(runSummary.baseUrl)}</div>
                </div>
                <div className="summary-item">
                  <div className="summary-label">模型名</div>
                  <div className="summary-value summary-value-small">{runSummary.modelName}</div>
                </div>
                <div className="summary-item">
                  <div className="summary-label">上下文档位</div>
                  <div className="summary-value summary-value-small">{contextModeLabels[runSummary.contextMode]}</div>
                </div>
                <div className="summary-item">
                  <div className="summary-label">已选探针</div>
                  <div className="summary-value summary-value-small">{runSummary.enabledProbes.length} 项</div>
                </div>
                <div className="summary-item">
                  <div className="summary-label">当前状态</div>
                  <div className="summary-value summary-value-small">{isRunning ? "检测中" : hasResult ? "检测完成" : "等待结果"}</div>
                </div>
              </div>
            </div>
          ) : null}

          <DetectorForm
            initialSummary={runSummary}
            isSubmitting={isRunning}
            onCompleted={onCompleted}
            onRunStart={handleRunStart}
            onSubmittingChange={onSubmittingChange}
          />
        </>
      )}
    </section>
  );
}
