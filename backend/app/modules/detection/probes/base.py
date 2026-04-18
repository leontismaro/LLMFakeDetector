from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.modules.detection.adapter import OpenAICompatibleAdapter
from app.modules.detection.schemas import DetectionRequest, ProbeFinding


@dataclass(slots=True)
class ProbeRuntime:
    request: DetectionRequest
    adapter: OpenAICompatibleAdapter


class DetectionProbe(ABC):
    name: str

    @abstractmethod
    async def run(self, runtime: ProbeRuntime) -> ProbeFinding:
        raise NotImplementedError
