import type { DetectionResponse } from "../features/detection/types";
import { DetectorForm } from "../features/detection/components/DetectorForm";

interface DetectorPageProps {
  onCompleted: (result: DetectionResponse) => void;
}

export function DetectorPage({ onCompleted }: DetectorPageProps) {
  return (
    <section className="card">
      <h2>检测入口</h2>
      <p>输入目标 API 的 Base URL、API Key 和模型名，当前会执行全部后端探针并返回结构化报告。</p>
      <DetectorForm onCompleted={onCompleted} />
    </section>
  );
}
