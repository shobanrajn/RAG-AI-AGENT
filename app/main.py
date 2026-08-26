import os
import sys

faq_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "faq"))
if faq_path not in sys.path:
    sys.path.insert(0, faq_path)

from fastapi import FastAPI
import app.faq.config as faq_config
from app.faq import logging as faq_logging
from app.faq.agent.retrieval import load_reranker
from app.api.router import router as api_v1_router
from app.middleware.cors import add_cors_middleware
from app.core.exceptions import add_exception_handlers

app = FastAPI()

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