# app/services/faq_service.py

import os
from app.faq.agent import invoke_faq_agent as invoke_gemini_faq_agent
from app.services.agent_runtime import invoke_faq_agent


async def handle_faq_flow(
    query_input,
    session_id,
    logger,
):
    retry_flag = 0

    # Route to Gemini RAG pipeline (app/faq/) or Bedrock agent based on FAQ_PROVIDER env var.
    # FAQ_PROVIDER=gemini -> pgvector retrieval + Gemini LLM (history auto-fetched inside agent.py)
    # FAQ_PROVIDER=bedrock (default) -> AWS Bedrock agent
    faq_provider = os.getenv("FAQ_PROVIDER", "bedrock").strip().lower()

    if faq_provider == "gemini":
        llm_response = await invoke_gemini_faq_agent(query=query_input, session_id=session_id)
    else:
        llm_response = invoke_faq_agent(query_input, session_id)

    logger.info(f"faq response : {llm_response}")

    response = llm_response.get("result_text", "")
    res_type = "json" if not isinstance(response, str) else "string"

    return {
        "response": response,
        "res_type": res_type,
        "retry_flag": 0,
    }