import time

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasicCredentials

from app.schemas.pydantic_schema import AgentRequest
from app.core.logging import setup_logger, create_log_name
from app.core.config import settings

from app.db.session import (
    create_mongo_connection,
    async_convo_log_mongo_insertion,
    async_convo_faq_mongo_insertion
)
from app.utils.redis_cache import create_redis_connection
from app.utils.pii_utils import strip_pii
from app.utils.text_utils import mobile_num_check, mobile_num_validation

from app.language.language_helper import get_language_mapping

from app.services.auth_service import validate_credentials
from app.services.spam_service import check_spam
from app.services.orchestrator import orchestrate_request
from app.services.response_service import build_final_response


async def process_agent_request(
    input_request: AgentRequest,
    credentials: HTTPBasicCredentials,
) -> JSONResponse:

    st = time.time()

    # =========================================================
    # Logger setup — mirrors create_log_name() from the raw file
    # =========================================================
    dt, timestamp = create_log_name()
    log_file_name = f"{settings.LOGGER_PATH}app_v1_{dt}.log"
    logger = setup_logger("app_logger", log_file_name)

    # =========================================================
    # AUTH
    # =========================================================
    try:
        await validate_credentials(credentials, logger)
    except HTTPException:
        detected_mobile_no = ""
        response = {
            "message": "Authorization issue",
            "detected_mobile_no": detected_mobile_no,
            "response_code": 401,
        }
        logger.info(f"final response : {response}")
        return JSONResponse(content=response)

    # =========================================================
    # DB + REDIS
    # =========================================================
    agent_col, lead_agent_col, crm_col, cust_col, histrory_col = (
        await create_mongo_connection(logger)
    )
    redis_client = create_redis_connection(logger)

    # =========================================================
    # INPUT EXTRACTION
    # =========================================================
    lang_code = input_request.selected_lang.lower()
    language_data = get_language_mapping(lang_code)
    intent_dict = language_data.get("intent_dict", {})

    query_input = input_request.query_input
    session_id = input_request.session_id
    mobile_no = input_request.mobile_no.lstrip("\n")
    user_request = input_request.user_request
    lead_capture = input_request.lead_capture
    show_more_req_flag = input_request.show_more_req_flag
    query_no = input_request.query_no
    user_text_flag = input_request.user_text_flag
    otp_verified = input_request.otp_verified
    verification_code = input_request.verification_code
    show_all_loans = input_request.show_all_loans

    redis_key_name = f"{session_id}_{query_no}"
    logger.info(f"incoming request: {input_request.model_dump_json()}")
    # =========================================================
    # SPAM CHECK — timestamp must be passed in
    # =========================================================
    is_spam, _ = await check_spam(
        agent_col=agent_col,
        query_input=query_input,
        timestamp=timestamp,
        logger=logger,
    )

    if is_spam:
        response = {
            "message": {
                "response": language_data.get("spam_message", "Being spammed"),
                "type": "string",
                "retry_flag": 0,
                "loan_api_failure_flag": 0,
            },
            "detected_mobile_no": "",
            "response_code": 206,
        }
        logger.info(f"final response : {response}")
        return JSONResponse(content=response)

    # =========================================================
    # PII SCRUB + MOBILE NUMBER DETECTION
    # =========================================================
    query_input = strip_pii(query_input, logger)
    detected_mobile_no = ""
    agreement_number = ""

    if lead_capture != "1":
        detected_mobile_no, agreement_number = mobile_num_check(
            query_input, logger
        )

    # Validate that the detected mobile matches the authenticated one
    mobile_num_detection_flag = True
    mobile_num_validation_flag = False

    if detected_mobile_no:
        mobile_num_detection_flag = False
        mobile_num_validation_flag = mobile_num_validation(
            mobile_no, detected_mobile_no, logger
        )

    if not (mobile_num_detection_flag or mobile_num_validation_flag):
        # Mobile number mismatch — short-circuit
        response_body = {
            "response": language_data.get(
                "mobile_mismatch_message",
                "The entered mobile number does not match our records."
            ),
            "type": "string",
            "retry_flag": 0,
            "loan_api_failure_flag": 0,
        }
        final = {
            "message": response_body,
            "detected_mobile_no": detected_mobile_no,
            "response_code": 205,
        }
        logger.info(f"final response : {final}")
        if agent_col is not None:
            await async_convo_log_mongo_insertion(
                logger, query_input, session_id, mobile_no,
                final, detected_mobile_no, timestamp, agent_col,
            )

        if user_request == "About Chola":
            if histrory_col is not None:
                await async_convo_faq_mongo_insertion(
                    logger,
                    query_input,
                    lang_code,
                    session_id,
                    mobile_no,
                    final,
                    detected_mobile_no,
                    timestamp,
                    histrory_col,
                )
            else:
                logger.warning("histrory_col is None")

        end_ = time.time()
        logger.info(f"total time taken : {end_ - st}")
        return JSONResponse(content=final)

    # Strip the detected mobile number from query before passing to LLM
    sub_str = "for product type"
    query_input = query_input.replace(detected_mobile_no, "")
    if sub_str in query_input:
        query_input = query_input[: query_input.find(sub_str)]
    logger.info(f"query sent to llm: {query_input}")

    # =========================================================
    # GREETING MESSAGE CHECK
    # =========================================================

    if str(query_input).lower() == "hi":
        response_body = {
        "response": language_data.get(
            "greeting_message",
            "Hello! How can I help you today?"
        ),
        "counter_flag_agg": 0,
        "intent_dict": {
            str(k): v
            for k, v in language_data.get("intent_dict", {}).items()
        },
        "type": "string",
        "retry_flag": 0,
        "loan_api_failure_flag": 0,
    }
        final = {
            "message": response_body,
            "detected_mobile_no": detected_mobile_no,
            "response_code": 200,
        }
        logger.info(f"final response : {final}")
        if agent_col is not None:
            await async_convo_log_mongo_insertion(
                logger, query_input, session_id, mobile_no,
                final, detected_mobile_no, timestamp, agent_col,
            )

        if user_request == "About Chola":
            if histrory_col is not None:
                await async_convo_faq_mongo_insertion(
                    logger,
                    query_input,
                    lang_code,
                    session_id,
                    mobile_no,
                    final,
                    detected_mobile_no,
                    timestamp,
                    histrory_col,
                )
            else:
                logger.warning("histrory_col is None")

        end_ = time.time()
        logger.info(f"total time taken : {end_ - st}")
        return JSONResponse(content=final)

    # =========================================================
    # ORCHESTRATION LAYER
    # =========================================================
    result = await orchestrate_request(
        query_input=query_input,
        session_id=session_id,
        mobile_no=mobile_no,
        user_request=user_request,
        lead_capture=lead_capture,
        input_request=input_request,
        logger=logger,
        agent_col=agent_col,
        lead_agent_col=lead_agent_col,
        crm_col=crm_col,
        cust_col=cust_col,
        redis_client=redis_client,
        redis_key_name=redis_key_name,
        timestamp=timestamp,
        language_data=language_data,
        detected_mobile_no=detected_mobile_no,
        agreement_number=agreement_number,
        otp_verified=otp_verified,
        verification_code=verification_code,
        show_more_req_flag=show_more_req_flag,
        user_text_flag=user_text_flag,
        show_all_loans=show_all_loans,
    )

    # =========================================================
    # FINAL RESPONSE WRAPPER
    # =========================================================
    agent_response = build_final_response(
        response=result["response"],
        detected_mobile_no=result.get("detected_mobile_no", detected_mobile_no),
        status_code=result["status_code"],
        res_type=result["res_type"],
        retry_flag=result["retry_flag"],
        loan_api_failure_flag=result.get("loan_api_failure_flag", 0),
    )

    # intent_dict keys must be strings (matches raw file guard)
    final = agent_response
    if (
        "message" in final
        and isinstance(final["message"], dict)
        and "intent_dict" in final["message"]
    ):
        final["message"]["intent_dict"] = {
            str(k): v for k, v in final["message"]["intent_dict"].items()
        }

    # Mongo conversation log
    if agent_col is not None:
        mongo_result = await async_convo_log_mongo_insertion(
            logger, query_input, session_id, mobile_no,
            final, result.get("detected_mobile_no", detected_mobile_no),
            timestamp, agent_col,
        )
        logger.info(f"mongo logger response : {mongo_result}")

    end_ = time.time()
    logger.info(f"final response : {final}")
    logger.info(f"total time taken : {end_ - st}")
    return JSONResponse(content=final)