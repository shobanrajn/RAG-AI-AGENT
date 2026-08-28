# app/services/faq_service.py
import os
from app.faq.agent import invoke_faq_agent as invoke_gemini_faq_agent

from app.services.agent_runtime import invoke_faq_agent


async def handle_faq_flow(
    query_input,
    session_id,
    logger,
):
    """
    Handles FAQ / About Chola flow.

    Returns a dict:
        {
            "response": <str or dict>,
            "res_type": "string" | "json",
            "retry_flag": 0 | 1,
        }
    """

    retry_flag = 0
    faq_provider = os.getenv("FAQ_PROVIDER", "bedrock").strip().lower()

     if faq_provider == "gemini":
        llm_response = await invoke_gemini_faq_agent(query=query_input, session_id=session_id)
    else:
        llm_response = invoke_faq_agent(query_input, session_id)

    logger.info(f"faq response : {llm_response}")
    logger.info(f"faq response type : {type(llm_response)}")

    if llm_response.get("status_code") == 300:
        retry_flag = 1

    response = llm_response.get("result_text", "")

    res_type = "json" if not isinstance(response, str) else "string"

    return {
        "response": response,
        "res_type": res_type,
        "retry_flag": 0,
        "retry_flag": retry_flag,
    }