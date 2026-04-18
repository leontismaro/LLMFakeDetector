import { useState } from "react";

import { runDetection } from "../api";
import type { DetectionResponse } from "../types";

interface DetectorFormProps {
  onCompleted: (result: DetectionResponse) => void;
}

export function DetectorForm({ onCompleted }: DetectorFormProps) {
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [modelName, setModelName] = useState("");
  const [message, setMessage] = useState("尚未发起检测。");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setMessage("检测执行中，正在等待后端返回结果。");

    try {
      const response = await runDetection({
        base_url: baseUrl,
        api_key: apiKey || undefined,
        model_name: modelName,
        enabled_probes: [],
      });
      setMessage(`检测已完成，当前信任分：${response.trust_score}`);
      onCompleted(response);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "检测失败");
    } finally {
      setIsSubmitting(false);
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

      <button className="primary-button" type="submit" disabled={isSubmitting}>
        {isSubmitting ? "检测中..." : "开始检测"}
      </button>

      <div className="form-hint">{message}</div>
    </form>
  );
}
