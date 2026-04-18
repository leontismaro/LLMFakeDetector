from app.modules.detection.probes.base import DetectionProbe, ProbeRuntime
from app.modules.detection.schemas import ProbeFinding


class BehaviorProbe(DetectionProbe):
    name = "behavior_probe"

    async def run(self, runtime: ProbeRuntime) -> ProbeFinding:
        return ProbeFinding(
            probe_name=self.name,
            status="skip",
            score=0,
            summary=f"{runtime.request.model_name} 的行为探针暂未纳入当前 MVP。",
            evidence=["后续会加入格式依从性、系统提示词泄露、长上下文行为等检测。"],
        )
