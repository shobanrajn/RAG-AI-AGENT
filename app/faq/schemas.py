from pydantic import BaseModel


class FAQRequest(BaseModel):
    query: str
    session_id: str


class FAQResponse(BaseModel):
    result_text: str
    label: str = "Rag-Agent"
