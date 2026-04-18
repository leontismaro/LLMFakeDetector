import { useState } from "react";

import { runDetection } from "../api";
import { PROBE_OPTIONS } from "../probeCatalog";
import type { ContextMode, DetectionResponse, DetectionRunSummary } from "../types";

interface DetectorFormProps {
  initialSummary?: DetectionRunSummary | null;
  isSubmitting: boolean;
  onCompleted: (result: DetectionResponse) => void;
  onRunStart: (summary: DetectionRunSummary) => void;
  onSubmittingChange: (submitting: boolean) => void;
}

export function DetectorForm({
  initialSummary,
  isSubmitting,
  onCompleted,
  onRunStart,
  onSubmittingChange,
}: DetectorFormProps) {
  const defaultEnabledProbes = PROBE_OPTIONS.map((option) => option.id);
  const [baseUrl, setBaseUrl] = useState(initialSummary?.baseUrl ?? "");
  const [apiKey, setApiKey] = useState(initialSummary?.apiKey ?? "");
  const [modelName, setModelName] = useState(initialSummary?.modelName ?? "");
  const [anthropicApiKey, setAnthropicApiKey] = useState(initialSummary?.anthropicApiKey ?? "");
  const [geminiApiKey, setGeminiApiKey] = useState(initialSummary?.geminiApiKey ?? "");
  const [contextMode, setContextMode] = useState<ContextMode>(initialSummary?.contextMode ?? "standard");
  const [enabledProbes, setEnabledProbes] = useState<string[]>(initialSummary?.enabledProbes ?? defaultEnabledProbes);
  const [message, setMessage] = useState("尚未发起检测。");

  const normalizedModelName = modelName.trim().toLowerCase();
  const shouldShowAnthropicReference = normalizedModelName.startsWith("claude");
  const shouldShowGeminiReference = normalizedModelName.startsWith("gemini");
  const allProbesSelected = enabledProbes.length === PROBE_OPTIONS.length;

  function handleProbeToggle(probeId: string) {
    setEnabledProbes((current) => {
      if (current.includes(probeId)) {
        return current.filter((item) => item !== probeId);
      }

      return [...current, probeId];
    });
  }

  function handleToggleAllProbes() {
    setEnabledProbes(allProbesSelected ? [] : defaultEnabledProbes);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const summary: DetectionRunSummary = {
      baseUrl: baseUrl.trim(),
      apiKey,
      modelName: modelName.trim(),
      contextMode,
      enabledProbes,
      anthropicApiKey,
      geminiApiKey,
    };

    onRunStart(summary);
    onSubmittingChange(true);
    setMessage("检测执行中，正在等待后端返回结果。");

    try {
      const response = await runDetection({
        base_url: baseUrl,
        api_key: apiKey || undefined,
        model_name: modelName,
        enabled_probes: enabledProbes,
        context_mode: contextMode,
        reference_options: {
          anthropic_api_key: anthropicApiKey || undefined,
          gemini_api_key: geminiApiKey || undefined,
        },
      });
      setMessage(`检测已完成，当前信任分：${response.trust_score}`);
      onCompleted(response);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "检测失败");
    } finally {
      onSubmittingChange(false);
    }
  }

  return (
    <form className="form-grid" onSubmit={handleSubmit}>
      <label>
        Base URL
        <input
          value={baseUrl}
          onChange={(event) => setBaseUrl(event.target.value)}
          placeholder="https://example.com/v1"
          disabled={isSubmitting}
        />
      </label>

      <label>
        API Key
        <input value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="sk-..." disabled={isSubmitting} />
      </label>

      <label>
        模型名
        <input value={modelName} onChange={(event) => setModelName(event.target.value)} placeholder="gpt-4o" disabled={isSubmitting} />
      </label>

      {shouldShowAnthropicReference ? (
        <label>
          Anthropic 官方 Key（可选）
          <input
            value={anthropicApiKey}
            onChange={(event) => setAnthropicApiKey(event.target.value)}
            placeholder="sk-ant-..."
            disabled={isSubmitting}
          />
          <span className="field-help">用于 Claude 官方输入 token 基线对比；不填写则自动跳过该项。</span>
        </label>
      ) : null}

      {shouldShowGeminiReference ? (
        <label>
          Gemini 官方 Key（可选）
          <input
            value={geminiApiKey}
            onChange={(event) => setGeminiApiKey(event.target.value)}
            placeholder="AIza..."
            disabled={isSubmitting}
          />
          <span className="field-help">用于 Gemini 官方输入 token 基线对比；不填写则自动跳过该项。</span>
        </label>
      ) : null}

      <label>
        上下文压测档位
        <select value={contextMode} onChange={(event) => setContextMode(event.target.value as ContextMode)} disabled={isSubmitting}>
          <option value="light">轻量：仅 small</option>
          <option value="standard">标准：small + medium</option>
          <option value="heavy">重度：small + medium + large</option>
        </select>
      </label>

      <fieldset className="probe-selector" disabled={isSubmitting}>
        <legend>运行探针</legend>
        <label className="probe-checkbox probe-checkbox-all">
          <input type="checkbox" checked={allProbesSelected} onChange={handleToggleAllProbes} />
          <span>
            <strong>全选探针</strong>
            <span className="field-help">当前共 {PROBE_OPTIONS.length} 项，可按需关闭高成本探针。</span>
          </span>
        </label>
        <div className="probe-option-grid">
          {PROBE_OPTIONS.map((probe) => (
            <label key={probe.id} className="probe-checkbox">
              <input
                type="checkbox"
                checked={enabledProbes.includes(probe.id)}
                onChange={() => handleProbeToggle(probe.id)}
              />
              <span>
                <strong>{probe.label}</strong>
                <span className="field-help">{probe.description}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <button className="primary-button" type="submit" disabled={isSubmitting || enabledProbes.length === 0}>
        {isSubmitting ? "检测中..." : "开始检测"}
      </button>

      <div className="form-hint">
        {enabledProbes.length === 0 ? "请至少选择一个探针后再开始检测。" : message}
      </div>
    </form>
  );
}
