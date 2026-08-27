from fastapi import APIRouter, Depends
from fastapi.security import HTTPBasicCredentials

from app.api.deps import verify_auth
from app.schemas.pydantic_schema import ImageExtractRequest
from app.services.image_service import image_process_service

router = APIRouter()


@router.post("/image_extract")
async def image_extract_v1(
    input_request: ImageExtractRequest,
    credentials: HTTPBasicCredentials = Depends(verify_auth)
):
    return await image_process_service(input_request, credentials)
