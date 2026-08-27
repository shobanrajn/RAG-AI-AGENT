from fastapi import APIRouter
from app.api.v1.agent import router as agent_router
from app.api.v1.connector import router as connector_router
from app.api.v1.image_extract import router as image_extract_router
from app.api.v1.name_match import router as name_match_router
from app.api.v1.image_merge import router as image_merge_router
from app.api.v1.hr_agent import router as hr_router


api_router = APIRouter()
router = api_router

api_router.include_router(agent_router, prefix="/v1", tags=["Agent"])
api_router.include_router(connector_router, prefix="/v1", tags=["Connector"])
api_router.include_router(image_extract_router, prefix="/v1", tags=["Image_Extract"])
api_router.include_router(name_match_router, prefix="/v1", tags=["Name_Match"])
api_router.include_router(image_merge_router, prefix="/v1", tags=["Image_Merge"])
api_router.include_router(hr_router, tags=["HR Agent"])
