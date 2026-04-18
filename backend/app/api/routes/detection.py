from fastapi import APIRouter

from app.modules.detection.schemas import DetectionRequest, DetectionResponse
from app.modules.detection.service import DetectionService

router = APIRouter()
service = DetectionService()


@router.post("/run", response_model=DetectionResponse)
async def run_detection(payload: DetectionRequest) -> DetectionResponse:
    return await service.run(payload)

