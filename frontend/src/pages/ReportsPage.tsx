import { useEffect, useMemo, useState } from "react";

import {
  getProbeLabel,
  getProbeOption,
  PROBE_GROUPS,
  type ProbeGroupId,
} from "../features/detection/probeCatalog";
import type {
  ContextMode,
  DetectionResponse,
  DetectionRunSummary,
  ProbeFinding,
  ProbeStatus,
} from "../features/detection/types";

interface ReportsPageProps {
  result: DetectionResponse | null;
  runSummary: DetectionRunSummary | null;
}

const statusLabels: Record<ProbeStatus, string> = {
  pass: "通过",
  warn: "警告",
  fail: "失败",
  skip: "跳过",
};

const contextModeLabels: Record<ContextMode, string> = {
  light: "轻量",
  standard: "标准",
  heavy: "重度",
};

const groupLabelMap = new Map(PROBE_GROUPS.map((group) => [group.id, group.label]));
const groupDescriptionMap = new Map(PROBE_GROUPS.map((group) => [group.id, group.description]));

function getContextProbeMeta(result: DetectionResponse | null): { contextMode?: string; selectedProfiles?: string[] } {
  if (!result) {
    return {};
  }

  const contextFinding = result.findings.find((finding) => finding.probe_name === "context_probe");
  const details = contextFinding?.details;
  const detailRecord = toRecord(details);
  if (!detailRecord) {
    return {};
  }

  const selectedProfiles = Array.isArray(detailRecord.selected_profiles)
    ? detailRecord.selected_profiles.filter((item): item is string => typeof item === "string")
    : undefined;

  return {
    contextMode: typeof detailRecord.context_mode === "string" ? detailRecord.context_mode : undefined,
    selectedProfiles,
  };
}

function formatValue(value: unknown): string {
  if (value === null) {
    return "null";
  }

  if (typeof value === "string") {
    return value;
  }

  return JSON.stringify(value, null, 2);
}

function toRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function toStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.length > 0) : [];
}

function toStatusMap(value: unknown): Record<string, string> | null {
  const record = toRecord(value);
  if (!record) {
    return null;
  }

  const entries = Object.entries(record).filter(([, item]) => typeof item === "string");
  return entries.length > 0 ? (Object.fromEntries(entries) as Record<string, string>) : null;
}

function formatLabel(value: string): string {
  return value.replace(/_/g, " ");
}

function renderStatusTag(value: string) {
  const normalized = value === "pass" || value === "warn" || value === "fail" || value === "skip" ? value : "skip";
  return <span className={`inline-status inline-status-${normalized}`}>{statusLabels[normalized]}</span>;
}

function normalizeStatus(value: unknown): ProbeStatus | null {
  return value === "pass" || value === "warn" || value === "fail" || value === "skip" ? value : null;
}

interface TokenizerSample {
  name: string;
  reference_tokens: number;
  observed_prompt_tokens: number;
  delta: number;
  http_version?: string;
}

function isTokenizerSample(value: unknown): value is TokenizerSample {
  const record = toRecord(value);
  return (
    record !== null &&
    typeof record.name === "string" &&
    typeof record.reference_tokens === "number" &&
    typeof record.observed_prompt_tokens === "number" &&
    typeof record.delta === "number"
  );
}

function TokenizerDetails({ details }: { details: Record<string, unknown> }) {
  const samples = Array.isArray(details.samples) ? details.samples.filter(isTokenizerSample) : [];
  const summaryEntries: Array<[string, unknown]> = [
    ["参考族", details.reference_family],
    ["参考来源", details.reference_source],
    ["参考模型", details.reference_model_name],
    ["参考编码", details.reference_encoding],
    ["样本数", details.sample_count],
    ["delta 范围", details.delta_range],
    ["负 delta 数", details.negative_delta_count],
    ["稳定样本数", details.stable_sample_count],
  ];
  const visibleSummaryEntries = summaryEntries.filter(([, value]) => value !== undefined);

  return (
    <div className="probe-details-stack">
      {visibleSummaryEntries.length > 0 ? (
        <section className="result-section">
          <strong>Tokenizer 指纹概览</strong>
          <div className="summary-grid compact-grid">
            {visibleSummaryEntries.map(([label, value]) => (
              <div key={label} className="summary-item">
                <div className="summary-label">{label}</div>
                <div className="summary-value">{String(value)}</div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {samples.length > 0 ? (
        <section className="result-section">
          <strong>样本对比</strong>
          <div className="table-shell">
            <table className="probe-table">
              <thead>
                <tr>
                  <th>样本</th>
                  <th>参考 tokens</th>
                  <th>观测 prompt_tokens</th>
                  <th>delta</th>
                  <th>HTTP</th>
                </tr>
              </thead>
              <tbody>
                {samples.map((sample) => (
                  <tr key={sample.name}>
                    <td>{sample.name}</td>
                    <td>{sample.reference_tokens}</td>
                    <td>{sample.observed_prompt_tokens}</td>
                    <td className={sample.delta < 0 ? "delta-negative" : "delta-positive"}>{sample.delta}</td>
                    <td>{sample.http_version ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  );
}

function BaselineChecks({ checks }: { checks: Record<string, string> }) {
  return (
    <section className="result-section">
      <strong>基线检查</strong>
      <div className="check-grid">
        {Object.entries(checks).map(([key, value]) => (
          <div key={key} className="check-item">
            <span className="check-name">{formatLabel(key)}</span>
            {renderStatusTag(value)}
          </div>
        ))}
      </div>
    </section>
  );
}

function KeyValueSection({ title, entries }: { title: string; entries: Array<[string, unknown]> }) {
  const filtered = entries.filter((entry): entry is [string, string | number | boolean] => {
    const [, value] = entry;
    return value !== undefined && value !== null && value !== "";
  });
  if (filtered.length === 0) {
    return null;
  }

  return (
    <section className="result-section">
      <strong>{title}</strong>
      <div className="summary-grid compact-grid">
        {filtered.map(([label, value]) => (
          <div key={label} className="summary-item">
            <div className="summary-label">{label}</div>
            <div className="summary-value summary-value-small">{String(value)}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ResponseHeaders({ headers }: { headers: Record<string, unknown> }) {
  const entries = Object.entries(headers).filter(([, value]) => typeof value === "string" && value.length > 0);
  if (entries.length === 0) {
    return null;
  }

  return (
    <section className="result-section">
      <strong>响应头</strong>
      <div className="header-grid">
        {entries.map(([key, value]) => (
          <div key={key} className="detail-item">
            <div className="detail-key">{key}</div>
            <div className="header-value">{String(value)}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ProbeCases({ cases }: { cases: Record<string, unknown> }) {
  const entries = Object.entries(cases)
    .map(([name, value]) => [name, toRecord(value)] as const)
    .filter((entry): entry is readonly [string, Record<string, unknown>] => entry[1] !== null);
  if (entries.length === 0) {
    return null;
  }

  const caseStatusCounts: Record<ProbeStatus, number> = { pass: 0, warn: 0, fail: 0, skip: 0 };
  entries.forEach(([, value]) => {
    const status = normalizeStatus(value.status);
    if (status) {
      caseStatusCounts[status] += 1;
    }
  });

  return (
    <section className="result-section">
      <div className="section-header">
        <strong>用例明细</strong>
        <div className="section-status-summary">
          {(["fail", "warn", "pass", "skip"] as ProbeStatus[])
            .filter((status) => caseStatusCounts[status] > 0)
            .map((status) => (
              <span key={status} className={`mini-status-badge mini-status-${status}`}>
                {statusLabels[status]} {caseStatusCounts[status]}
              </span>
            ))}
        </div>
      </div>
      <div className="case-grid">
        {entries.map(([name, value]) => {
          const responseHeaders = toRecord(value.response_headers);
          const mismatchPaths = toStringArray(value.mismatch_paths);
          const status = normalizeStatus(value.status);
          return (
            <article key={name} className={`case-card${status ? ` case-card-${status}` : ""}`}>
              <div className="case-header">
                <div className="case-title">{formatLabel(name)}</div>
                {status ? renderStatusTag(status) : null}
              </div>
              <div className="case-meta">
                <span>HTTP {String(value.status_code ?? "-")}</span>
                {typeof value.http_version === "string" ? <span>{value.http_version}</span> : null}
                {typeof value.tool_call_count === "number" ? <span>tool_calls {value.tool_call_count}</span> : null}
                {typeof value.selected_tool_name === "string" ? <span>tool {value.selected_tool_name}</span> : null}
                {typeof value.deviation_kind === "string" ? <span>{value.deviation_kind}</span> : null}
              </div>
              {typeof value.observed_content === "string" ? (
                <pre className="detail-value">{value.observed_content}</pre>
              ) : null}
              {mismatchPaths.length > 0 ? (
                <div className="detail-item">
                  <div className="detail-key">mismatch paths</div>
                  <div className="detail-value-inline">{mismatchPaths.join(", ")}</div>
                </div>
              ) : null}
              {value.parsed_arguments !== undefined ? (
                <div className="detail-item">
                  <div className="detail-key">parsed arguments</div>
                  <pre className="detail-value">{formatValue(value.parsed_arguments)}</pre>
                </div>
              ) : null}
              {responseHeaders ? <ResponseHeaders headers={responseHeaders} /> : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function GenericDetailGrid({ details }: { details: Record<string, unknown> }) {
  const ignoredKeys = new Set([
    "samples",
    "baseline_checks",
    "baseline_matches",
    "baseline_risks",
    "response_headers",
    "cases",
    "endpoint_url",
    "http_version",
    "system_fingerprint",
    "reference_family",
    "reference_encoding",
    "sample_count",
    "delta_range",
    "negative_delta_count",
    "stable_sample_count",
  ]);

  const entries = Object.entries(details).filter(([key]) => !ignoredKeys.has(key));
  if (entries.length === 0) {
    return null;
  }

  return (
    <section className="result-section">
      <strong>其他细节</strong>
      <div className="detail-grid">
        {entries.map(([key, value]) => (
          <div key={key} className="detail-item">
            <div className="detail-key">{key}</div>
            <pre className="detail-value">{formatValue(value)}</pre>
          </div>
        ))}
      </div>
    </section>
  );
}

function ProbeDetails({ finding }: { finding: ProbeFinding }) {
  const details = toRecord(finding.details);
  if (!details) {
    return null;
  }

  const baselineChecks = toStatusMap(details.baseline_checks);
  const baselineMatches = toStringArray(details.baseline_matches);
  const baselineRisks = toStringArray(details.baseline_risks);
  const responseHeaders = toRecord(details.response_headers);
  const cases = toRecord(details.cases);

  return (
    <div className="probe-details-stack">
      <KeyValueSection
        title="请求元数据"
        entries={[
          ["接口地址", details.endpoint_url],
          ["HTTP 版本", details.http_version],
          ["system_fingerprint", details.system_fingerprint],
          ["失败类型", details.failure_kind],
          ["失败样本", details.sample_name],
        ]}
      />

      {finding.probe_name === "tokenizer_probe" ? <TokenizerDetails details={details} /> : null}
      {baselineChecks ? <BaselineChecks checks={baselineChecks} /> : null}
      {baselineMatches.length > 0 ? (
        <div className="result-section">
          <strong>基线匹配信号</strong>
          <ul className="plain-list">
            {baselineMatches.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {baselineRisks.length > 0 ? (
        <div className="result-section">
          <strong>基线偏离信号</strong>
          <ul className="plain-list">
            {baselineRisks.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {cases ? <ProbeCases cases={cases} /> : null}
      {responseHeaders ? <ResponseHeaders headers={responseHeaders} /> : null}
      <GenericDetailGrid details={details} />
    </div>
  );
}

function ProbeSummarySections({ finding }: { finding: ProbeFinding }) {
  const evidence = finding.evidence.filter((item) => item.length > 0);
  const keyEvidence = evidence.slice(0, 2);
  const remainingEvidence = evidence.slice(2);

  return (
    <>
      {keyEvidence.length > 0 ? (
        <div className="result-section">
          <strong>关键信号</strong>
          <ul className="plain-list">
            {keyEvidence.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {remainingEvidence.length > 0 ? (
        <div className="result-section">
          <strong>补充证据</strong>
          <ul className="plain-list">
            {remainingEvidence.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <ProbeDetails finding={finding} />
    </>
  );
}

function ProbeListItem({
  finding,
  selected,
  onSelect,
}: {
  finding: ProbeFinding;
  selected: boolean;
  onSelect: () => void;
}) {
  const probeOption = getProbeOption(finding.probe_name);
  const groupLabel = probeOption ? groupLabelMap.get(probeOption.groupId) : undefined;

  return (
    <button
      type="button"
      className={`probe-list-item status-${finding.status}${selected ? " is-selected" : ""}`}
      onClick={onSelect}
    >
      <div className="probe-list-top">
        {groupLabel ? <span className="probe-group-badge">{groupLabel}</span> : null}
        <div className="probe-list-badges">
          <span className={`status-badge status-${finding.status}`}>{statusLabels[finding.status]}</span>
          <span className="score-badge">{finding.score}</span>
        </div>
      </div>
      <div className="probe-list-title">{getProbeLabel(finding.probe_name)}</div>
      <div className="probe-list-summary">{finding.summary}</div>
    </button>
  );
}

function ProbeDetailPanel({ finding }: { finding: ProbeFinding }) {
  const probeOption = getProbeOption(finding.probe_name);
  const groupLabel = probeOption ? groupLabelMap.get(probeOption.groupId) : undefined;

  return (
    <article className={`result-item detail-panel status-${finding.status}`}>
      <header className="result-header">
        <div className="result-header-main">
          <div className="result-title-row">
            {groupLabel ? <span className="probe-group-badge">{groupLabel}</span> : null}
            <h3>{getProbeLabel(finding.probe_name)}</h3>
          </div>
          <p className="result-summary">{finding.summary}</p>
        </div>
        <div className="result-badges">
          <div className="badge-stack">
            <span className="badge-label">状态</span>
            <span className={`status-badge status-${finding.status}`}>{statusLabels[finding.status]}</span>
          </div>
          <div className="badge-stack">
            <span className="badge-label">分数</span>
            <span className="score-badge">{finding.score}</span>
          </div>
        </div>
      </header>
      <ProbeSummarySections finding={finding} />
    </article>
  );
}

function formatBaseUrl(value: string): string {
  try {
    const url = new URL(value);
    return url.host || value;
  } catch {
    return value;
  }
}

export function ReportsPage({ result, runSummary }: ReportsPageProps) {
  const contextMeta = getContextProbeMeta(result);
  const [activeGroup, setActiveGroup] = useState<"all" | ProbeGroupId>("all");
  const [activeStatus, setActiveStatus] = useState<"all" | ProbeStatus>("all");
  const [selectedProbeName, setSelectedProbeName] = useState<string | null>(null);
  const statusCounts = useMemo(() => {
    const initial: Record<ProbeStatus, number> = { pass: 0, warn: 0, fail: 0, skip: 0 };
    (result?.findings ?? []).forEach((finding) => {
      initial[finding.status] += 1;
    });
    return initial;
  }, [result]);
  const groupCounts = useMemo(() => {
    const initial = new Map<ProbeGroupId, number>();
    (result?.findings ?? []).forEach((finding) => {
      const groupId = getProbeOption(finding.probe_name)?.groupId ?? "protocol";
      initial.set(groupId, (initial.get(groupId) ?? 0) + 1);
    });
    return initial;
  }, [result]);
  const visibleFindings = useMemo(() => {
    const severityOrder: Record<ProbeStatus, number> = { fail: 0, warn: 1, pass: 2, skip: 3 };
    const groupOrder = new Map(PROBE_GROUPS.map((group, index) => [group.id, index]));

    return (result?.findings ?? [])
      .filter((finding) => {
        const groupId = getProbeOption(finding.probe_name)?.groupId ?? "protocol";
        const groupMatched = activeGroup === "all" || groupId === activeGroup;
        const statusMatched = activeStatus === "all" || finding.status === activeStatus;
        return groupMatched && statusMatched;
      })
      .sort((left, right) => {
        const statusDelta = severityOrder[left.status] - severityOrder[right.status];
        if (statusDelta !== 0) {
          return statusDelta;
        }

        const leftGroup = getProbeOption(left.probe_name)?.groupId ?? "protocol";
        const rightGroup = getProbeOption(right.probe_name)?.groupId ?? "protocol";
        const groupDelta = (groupOrder.get(leftGroup) ?? 0) - (groupOrder.get(rightGroup) ?? 0);
        if (groupDelta !== 0) {
          return groupDelta;
        }

        return right.score - left.score;
      });
  }, [activeGroup, activeStatus, result]);
  const selectedFinding = useMemo(
    () => visibleFindings.find((finding) => finding.probe_name === selectedProbeName) ?? visibleFindings[0] ?? null,
    [selectedProbeName, visibleFindings],
  );

  useEffect(() => {
    if (!selectedFinding) {
      setSelectedProbeName(null);
      return;
    }

    if (selectedProbeName !== selectedFinding.probe_name) {
      setSelectedProbeName(selectedFinding.probe_name);
    }
  }, [selectedFinding, selectedProbeName]);

  return (
    <section className="card report-card">
      <div className="report-header">
        <div>
          <h2>报告视图</h2>
        </div>
      </div>
      {result ? (
        <>
          <div className="report-overview">
            <div>
              <div className="metric-label">模型名</div>
              <div className="metric-value">{result.model_name}</div>
            </div>
            <div>
              <div className="metric-label">信任分</div>
              <div className="metric-value">{result.trust_score}</div>
            </div>
            <div>
              <div className="metric-label">探针数</div>
              <div className="metric-value">{result.findings.length}</div>
            </div>
            <div>
              <div className="metric-label">通过 / 警告 / 失败</div>
              <div className="metric-value metric-value-compact">
                {statusCounts.pass} / {statusCounts.warn} / {statusCounts.fail}
              </div>
            </div>
            {runSummary ? (
              <div>
                <div className="metric-label">目标地址</div>
                <div className="metric-value metric-value-compact">{formatBaseUrl(runSummary.baseUrl)}</div>
              </div>
            ) : null}
            {runSummary ? (
              <div>
                <div className="metric-label">已选探针</div>
                <div className="metric-value metric-value-compact">{runSummary.enabledProbes.length} 项</div>
              </div>
            ) : null}
            {contextMeta.contextMode ? (
              <div>
                <div className="metric-label">上下文档位</div>
                <div className="metric-value metric-value-compact">
                  {contextModeLabels[contextMeta.contextMode as ContextMode] ?? contextMeta.contextMode}
                </div>
              </div>
            ) : null}
            {contextMeta.selectedProfiles && contextMeta.selectedProfiles.length > 0 ? (
              <div>
                <div className="metric-label">上下文用例</div>
                <div className="metric-value metric-value-compact">{contextMeta.selectedProfiles.join(" + ")}</div>
              </div>
            ) : null}
          </div>

          <div className="report-toolbar">
            <div className="filter-section">
              <div className="filter-chip-row">
                <button
                  type="button"
                  className={`filter-chip${activeGroup === "all" ? " is-active" : ""}`}
                  onClick={() => setActiveGroup("all")}
                >
                  全部
                  <span className="filter-chip-count">{result.findings.length}</span>
                </button>
                {PROBE_GROUPS.map((group) => (
                  <button
                    key={group.id}
                    type="button"
                    className={`filter-chip${activeGroup === group.id ? " is-active" : ""}`}
                    onClick={() => setActiveGroup(group.id)}
                    title={groupDescriptionMap.get(group.id)}
                  >
                    {group.label}
                    <span className="filter-chip-count">{groupCounts.get(group.id) ?? 0}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="filter-section">
              <div className="filter-chip-row">
                <button
                  type="button"
                  className={`filter-chip${activeStatus === "all" ? " is-active" : ""}`}
                  onClick={() => setActiveStatus("all")}
                >
                  全部
                  <span className="filter-chip-count">{result.findings.length}</span>
                </button>
                {(["fail", "warn", "pass", "skip"] as ProbeStatus[]).map((status) => (
                  <button
                    key={status}
                    type="button"
                    className={`filter-chip filter-chip-${status}${activeStatus === status ? " is-active" : ""}`}
                    onClick={() => setActiveStatus(status)}
                  >
                    {statusLabels[status]}
                    <span className="filter-chip-count">{statusCounts[status]}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="results-workspace">
            <aside className="results-sidebar">
              <div className="results-sidebar-header">
                <strong>探针目录</strong>
                <span>{visibleFindings.length} 项</span>
              </div>
              <div className="probe-list">
                {visibleFindings.map((finding) => (
                  <ProbeListItem
                    key={finding.probe_name}
                    finding={finding}
                    selected={selectedFinding?.probe_name === finding.probe_name}
                    onSelect={() => setSelectedProbeName(finding.probe_name)}
                  />
                ))}
              </div>
            </aside>

            <section className="results-detail">
              {selectedFinding ? <ProbeDetailPanel finding={selectedFinding} /> : <p>当前筛选条件下没有匹配的探针。</p>}
            </section>
          </div>
        </>
      ) : (
        <p>当前还没有真实检测结果。</p>
      )}
    </section>
  );
}
