from fastapi import FastAPI
from app.api.router import router as api_v1_router
from app.middleware.cors import add_cors_middleware
from app.core.exceptions import add_exception_handlers
# from app.core.logging import setup_logging
from contextlib import asynccontextmanager
from app.db.session import init_mongo_client, close_mongo_client

#app = FastAPI()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # At the startup - init the shared mongo client
    init_mongo_client()
    yield
    # On shutdown — cleanly closes all the pooled connections within the mongo client
    close_mongo_client()

app = FastAPI(lifespan=lifespan)

# setup_logging()
add_cors_middleware(app)
add_exception_handlers(app)

app.include_router(api_v1_router)

@app.on_event("startup")
def startup_faq_modules():
    faq_logging._cleanup_old_logs()
    load_reranker()

@app.get("/")
def root():
    return {"message": "Agent is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)
