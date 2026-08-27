from fastapi import APIRouter, Depends
from fastapi.security import HTTPBasicCredentials
from app.api.deps import verify_auth
from app.schemas.pydantic_schema import ImageMergeRequest
from app.services.merge_image_service import merge_images

router = APIRouter()


@router.post("/image_merge")
async def image_merge_v1(
    input_request: ImageMergeRequest,
    credentials: HTTPBasicCredentials = Depends(verify_auth)
):
    """
    Unified image processing endpoint that handles:
    - Single image conversion: Provide only 'first_image' (converts to JPEG, handles multi-page PDFs)
    - Image merge: Provide both 'first_image' and 'second_image' (merges vertically)
    """
    return await merge_images(input_request, credentials)
