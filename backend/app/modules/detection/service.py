import httpx

from app.core.config import settings
from app.modules.detection.adapter import OpenAICompatibleAdapter
from app.modules.detection.probes.registry import build_default_probes
from app.modules.detection.probes.base import ProbeRuntime
from app.modules.detection.schemas import DetectionRequest, DetectionResponse, ProbeFinding


class DetectionService:
    def __init__(self) -> None:
        self._probes = build_default_probes()

    async def run(self, request: DetectionRequest) -> DetectionResponse:
        findings: list[ProbeFinding] = []
        async with httpx.AsyncClient(
            timeout=settings.default_timeout_seconds,
            trust_env=settings.use_env_proxy,
        ) as client:
            runtime = ProbeRuntime(
                request=request,
                adapter=OpenAICompatibleAdapter(request=request, client=client),
            )

            for probe in self._probes:
                if request.enabled_probes and probe.name not in request.enabled_probes:
                    continue

                try:
                    findings.append(await probe.run(runtime))
                except httpx.HTTPError as exc:
                    findings.append(
                        ProbeFinding(
                            probe_name=probe.name,
                            status="fail",
                            score=0,
                            summary="探针执行失败，目标接口不可达或请求链路异常。",
                            evidence=[str(exc)],
                            details={"endpoint_url": runtime.adapter.endpoint_url},
                        )
                    )
                except Exception as exc:  # pragma: no cover
                    findings.append(
                        ProbeFinding(
                            probe_name=probe.name,
                            status="fail",
                            score=0,
                            summary="探针执行失败，内部检测逻辑出现未处理异常。",
                            evidence=[str(exc)],
                            details={"endpoint_url": runtime.adapter.endpoint_url},
                        )
                    )

        trust_score = self._calculate_trust_score(findings)
        return DetectionResponse(
            model_name=request.model_name,
            trust_score=trust_score,
            findings=findings,
        )

    @staticmethod
    def _calculate_trust_score(findings: list[ProbeFinding]) -> int:
        scored_findings = [finding for finding in findings if finding.status != "skip"]
        if not scored_findings:
            return 0
        return int(sum(finding.score for finding in scored_findings) / len(scored_findings))
