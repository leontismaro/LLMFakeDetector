import type { PropsWithChildren } from "react";

interface PageShellProps extends PropsWithChildren {
  isDetectorCollapsed?: boolean;
}

export function PageShell({ children, isDetectorCollapsed = false }: PageShellProps) {
  return (
    <main className="page-shell">
      <section className="hero">
        <h1>LLM Fake Detector</h1>
        <p>面向 API 中转、企业网关和模型降级场景的真伪核验工具。</p>
      </section>
      <section className={`grid${isDetectorCollapsed ? " grid-detector-collapsed" : ""}`}>{children}</section>
    </main>
  );
}
