import type { DetectionRequest, DetectionResponse } from "./types";

export async function runDetection(payload: DetectionRequest): Promise<DetectionResponse> {
  const response = await fetch("/api/detections/run", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let message = "检测请求失败";

    try {
      const data = (await response.json()) as { detail?: string };
      if (typeof data.detail === "string" && data.detail.trim()) {
        message = data.detail;
      }
    } catch {
      // 保持默认错误信息，避免二次解析掩盖原始失败。
    }

    throw new Error(message);
  }

  return response.json() as Promise<DetectionResponse>;
}
