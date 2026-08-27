from fastapi import APIRouter, Depends
from fastapi.security import HTTPBasicCredentials
from app.api.deps import verify_auth
from app.schemas.pydantic_schema import NameMatchRequest
from app.services.name_match_service import match_names

router = APIRouter()


@router.post("/name_match")
async def name_match_v1(
    input_request: NameMatchRequest,
    credentials: HTTPBasicCredentials = Depends(verify_auth)
):
    return await match_names(input_request, credentials)
