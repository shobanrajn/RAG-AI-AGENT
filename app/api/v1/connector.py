from fastapi import APIRouter, Depends
from fastapi.security import HTTPBasicCredentials

from app.api.deps import verify_auth
from app.schemas.pydantic_schema import QueryRequest

from app.services.connector_service import process_connector_request

router = APIRouter()


@router.post("/connector")
async def connector_v1(
    input_request: QueryRequest,
    credentials: HTTPBasicCredentials = Depends(verify_auth)
):
    return await process_connector_request(input_request, credentials)
