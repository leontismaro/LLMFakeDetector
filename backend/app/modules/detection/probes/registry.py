from app.modules.detection.probes.behavior_probe import BehaviorProbe
from app.modules.detection.probes.base import DetectionProbe
from app.modules.detection.probes.context_probe import ContextProbe
from app.modules.detection.probes.error_probe import ErrorResponseProbe
from app.modules.detection.probes.function_calling_probe import FunctionCallingProbe
from app.modules.detection.probes.gateway_signature_probe import GatewaySignatureProbe
from app.modules.detection.probes.logprobs_probe import LogprobsProbe
from app.modules.detection.probes.parameter_probe import ParameterProbe
from app.modules.detection.probes.response_probe import ResponseProbe
from app.modules.detection.probes.tokenizer_probe import TokenizerProbe
from app.modules.detection.probes.vision_probe import VisionProbe


def build_default_probes() -> list[DetectionProbe]:
    return [
        ParameterProbe(),
        FunctionCallingProbe(),
        VisionProbe(),
        GatewaySignatureProbe(),
        TokenizerProbe(),
        LogprobsProbe(),
        ResponseProbe(),
        BehaviorProbe(),
        ContextProbe(),
        ErrorResponseProbe(),
    ]
