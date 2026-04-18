from app.modules.detection.probes.behavior_probe import BehaviorProbe
from app.modules.detection.probes.base import DetectionProbe
from app.modules.detection.probes.error_probe import ErrorResponseProbe
from app.modules.detection.probes.logprobs_probe import LogprobsProbe
from app.modules.detection.probes.parameter_probe import ParameterProbe
from app.modules.detection.probes.response_probe import ResponseProbe
from app.modules.detection.probes.tokenizer_probe import TokenizerProbe


def build_default_probes() -> list[DetectionProbe]:
    return [
        ParameterProbe(),
        TokenizerProbe(),
        LogprobsProbe(),
        ResponseProbe(),
        BehaviorProbe(),
        ErrorResponseProbe(),
    ]
