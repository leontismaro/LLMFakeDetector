import type { PropsWithChildren } from "react";

export function PageShell({ children }: PropsWithChildren) {
  return (
    <main className="page-shell">
      <section className="hero">
        <h1>LLM Fake Detector</h1>
        <p>
          面向 API 中转、企业网关和模型降级场景的真伪核验工具。当前版本先固定项目结构和模块边界，后续逐步补充真实探针。
        </p>
      </section>
      <section className="grid">{children}</section>
    </main>
  );
}
