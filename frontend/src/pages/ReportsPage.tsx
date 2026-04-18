import type { DetectionResponse, ProbeFinding, ProbeStatus } from "../features/detection/types";

interface ReportsPageProps {
  result: DetectionResponse | null;
}

const statusLabels: Record<ProbeStatus, string> = {
  pass: "通过",
  warn: "警告",
  fail: "失败",
  skip: "跳过",
};

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
  return entries.length > 0 ? Object.fromEntries(entries) as Record<string, string> : null;
}

function formatLabel(value: string): string {
  return value.replace(/_/g, " ");
}

function renderStatusTag(value: string) {
  const normalized = value === "pass" || value === "warn" || value === "fail" || value === "skip" ? value : "skip";

  return <span className={`inline-status inline-status-${normalized}`}>{value}</span>;
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

  return (
    <section className="result-section">
      <strong>用例明细</strong>
      <div className="case-grid">
        {entries.map(([name, value]) => {
          const responseHeaders = toRecord(value.response_headers);
          return (
            <article key={name} className="case-card">
              <div className="case-title">{formatLabel(name)}</div>
              <div className="case-meta">
                {typeof value.status === "string" ? <span>{value.status}</span> : null}
                <span>HTTP {String(value.status_code ?? "-")}</span>
                {typeof value.http_version === "string" ? <span>{value.http_version}</span> : null}
                {typeof value.tool_call_count === "number" ? <span>tool_calls {value.tool_call_count}</span> : null}
                {typeof value.deviation_kind === "string" ? <span>{value.deviation_kind}</span> : null}
              </div>
              {typeof value.observed_content === "string" ? (
                <pre className="detail-value">{value.observed_content}</pre>
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

function ProbeCard({ finding }: { finding: ProbeFinding }) {
  const evidence = finding.evidence.filter((item) => item.length > 0);

  return (
    <article className={`result-item status-${finding.status}`}>
      <header className="result-header">
        <div>
          <h4>{finding.probe_name}</h4>
          <p className="result-summary">{finding.summary}</p>
        </div>
        <div className="result-badges">
          <span className={`status-badge status-${finding.status}`}>{statusLabels[finding.status]}</span>
          <span className="score-badge">{finding.score}</span>
        </div>
      </header>

      {evidence.length > 0 ? (
        <div className="result-section">
          <strong>证据</strong>
          <ul className="plain-list">
            {evidence.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <ProbeDetails finding={finding} />
    </article>
  );
}

export function ReportsPage({ result }: ReportsPageProps) {
  return (
    <section className="card">
      <h2>报告视图</h2>
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
          </div>

          <div className="result-list">
            {result.findings.map((finding) => (
              <ProbeCard key={finding.probe_name} finding={finding} />
            ))}
          </div>
        </>
      ) : (
        <p>当前还没有真实检测结果。提交一次检测后，这里会展示信任分、探针结论、证据和响应细节。</p>
      )}
    </section>
  );
}
