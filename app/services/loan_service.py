# app/services/loan_service.py

import json

from app.core.config import settings
from app.db.session import async_cust_log_mongo_insertion
from app.core.http_client import async_client
from app.services.entity_mapping import entity_mapping
from app.utils.redis_cache import retrieve_data_redis
from app.utils.text_utils import (
    check_agent_response,
    convert_to_dict_if_possible,
    user_text_check,
)


# ---------------------------------------------------------------------------
# Customer verification (Apply Loan flow)
# ---------------------------------------------------------------------------

async def loan_against_mobilenumber(mobile_num, cust_col, logger, timestamp):
    """
    Customer verification API call used in Apply Loan flow.
    """

    try:
        loan_url = settings.LOAN_URL

        payload = json.dumps(
            {
                "loanaccno": mobile_num,
                "source_system": "bedrock_cholaone_agent",
                "logintype": "M",
                "activity": "LOGINAUTH",
            }
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": settings.LOAN_URL_TOKEN,
        }

        response = await async_client.post(
            loan_url, headers=headers, content=payload
        )

        logger.info(f"response in loan_against_mobilenumber: {response}")

        response_json = response.json()

        logger.info(
            f"response in loan_against_mobilenumber in json: {response_json}"
        )

        cust_insert_resp = await async_cust_log_mongo_insertion(
            logger, mobile_num, response_json, timestamp, cust_col
        )

        logger.info(f"customer check captured in mongo: {cust_insert_resp}")

        return response_json

    except Exception as e:
        logger.exception(f"exception in loan_against_mobilenumber: {e}")
        return None


# ---------------------------------------------------------------------------
# Multi-loan selection
# ---------------------------------------------------------------------------

async def loan_details_based_on_agreement(
    entity_loan_details,
    query_input,
    mobile_no,
    detected_mobile_no,
    agreement_number,
    session_id,
    logger,
    redis_client,
    redis_key_name,
    entity,
    show_all_loans,
):
    """
    Handles multi-loan selection flow.

    Scenarios:
        0 loans  → message: no loans available
        1 loan   → auto-selects, returns agreement number
        2+ loans → prompts user to pick one
    """

    logger.info("inside the function loan_details_based_on_agreement")

    multi_loan_flag = 0
    api_resp = {}
    resp_count = 0

    try:
        (
            api_resp,
            resp_count,
            rem_flag,
            loan_api_failure_flag,
        ) = await entity_mapping(
            entity_loan_details,
            query_input,
            mobile_no,
            detected_mobile_no,
            agreement_number,
            session_id,
            logger,
            redis_client,
            redis_key_name,
            show_all_loans,
        )

        if resp_count == 0:
            api_resp["message_text"] = (
                "No loans available under this mobile number"
            )
            api_resp["multi_loan_flag"] = multi_loan_flag
            api_resp["identified_intent"] = entity
            api_resp["agreement_number"] = agreement_number

        elif resp_count == 1:
            agreement_number = api_resp["response"][0]["agreement_number"]
            api_resp["message_text"] = "You have only one loan registered"
            api_resp["multi_loan_flag"] = multi_loan_flag
            api_resp["identified_intent"] = entity
            api_resp["agreement_number"] = agreement_number

        else:
            multi_loan_flag = 1
            api_resp["message_text"] = (
                "You have multiple loans. Please choose one among them."
            )
            api_resp["multi_loan_flag"] = multi_loan_flag
            api_resp["identified_intent"] = entity
            api_resp["agreement_number"] = agreement_number

        logger.info(f"api_resp : {api_resp}\n resp_count : {resp_count}")
        return api_resp, resp_count

    except Exception as e:
        logger.exception(e)
        # Return the partially-filled api_resp and resp_count so
        # callers don't get a bare empty dict on partial failures.
        return api_resp, resp_count


# ---------------------------------------------------------------------------
# My Loans flow (full OTP + SR intent + entity-mapping path)
# ---------------------------------------------------------------------------

async def handle_my_loans_flow(
    *,
    input_request,
    query_input,
    session_id,
    mobile_no,
    detected_mobile_no,
    agreement_number,
    logger,
    language_data,
    redis_client,
    redis_key_name,
    show_all_loans,
):
    """
    Complete My Loans flow extracted from the raw file.

    Covers:
        - OTP generate
        - OTP verify (with early-return on failure)
        - SR intent detection
        - Entity mapping + loan detail retrieval
        - Response formatting via formatter_service

    Returns a result dict with keys:
        response, res_type, status_code, retry_flag,
        loan_api_failure_flag, detected_mobile_no
    """
    
    from app.core.constants import (
        ENTITY_LIMITED_LIST,
        ENTITY_SUPER_LIST,
        FLOW_RELATED,
        SR_INTENT_LIST,
    )
    from app.services.otp_service import generate_otp_service, verify_otp_service
    from app.services.formatter_service import (
        format_entity_response,
        NON_DICT_CONVERSION_ENTITIES,
    )

    otp_verified = input_request.otp_verified
    verification_code = input_request.verification_code
    show_more_req_flag = input_request.show_more_req_flag
    user_text_flag = input_request.user_text_flag

    entity_loan_details = "loan_details_"
    phrase = "i will ask"

    response = {}
    res_type = "string"
    status_code = 200
    retry_flag = 0
    loan_api_failure_flag = 0
    sr_flag = 0
    entity = ""
    default_flag = 0
    resp_count = 0
    rem_flag = 0
    loan_count = 0
    api_resp = {}

    # ------------------------------------------------------------------
    # OTP GENERATE
    # ------------------------------------------------------------------
    if query_input == "otp_generate":
        logger.info("Inside OTP Generate in APP")
        await generate_otp_service(mobile_no, logger)
        res_type = "string"
        response["response"] = language_data.get(
            "otp_request_message", "Please enter your otp..."
        )
        response["flow_type"] = "otp_generate"

        return {
            "response": response,
            "res_type": res_type,
            "status_code": status_code,
            "retry_flag": retry_flag,
            "loan_api_failure_flag": loan_api_failure_flag,
            "detected_mobile_no": detected_mobile_no,
        }

    # ------------------------------------------------------------------
    # OTP VERIFY
    # ------------------------------------------------------------------
    if query_input == "otp_verify":
        otp_verify_response = await verify_otp_service(
            mobile_no, verification_code, logger
        )

        response["flow_type"] = "otp_verify"

        if otp_verify_response.get("success"):
            response["otp_verified"] = "1"
            otp_verified = "1"
            # Fall through to the main loan-detail path with a default query
            query_input = "Show my loan details"
        else:
            response["otp_verified"] = "0"
            response["response"] = language_data.get(
                "otp_fail_message", "Invalid OTP. Please try again."
            )
            response["loan_api_failure_flag"] = 0
            response["type"] = "string"
            response["retry_flag"] = "string"

            if detected_mobile_no is None:
                detected_mobile_no = ""

            return {
                "response": response,
                "res_type": "string",
                "status_code": 208,
                "retry_flag": retry_flag,
                "loan_api_failure_flag": 0,
                "detected_mobile_no": detected_mobile_no,
            }

    # ------------------------------------------------------------------
    # OTP-GATED: LOAN DETAIL RETRIEVAL
    # ------------------------------------------------------------------
    if otp_verified == "1":
        logger.info(f"query_input : {query_input}")

        if show_more_req_flag == "0":

            # ----------------------------------------------------------
            # SR intent detection
            # ----------------------------------------------------------
            if user_text_flag:
                sr_flag, entity = user_text_check(query_input, logger)
                logger.info(f"entity: {entity}")

            if int(sr_flag) == 0:
                from app.services.intent_service import detect_sr_intent

                sr_result = await detect_sr_intent(
                    query_input=query_input,
                    session_id=session_id,
                    logger=logger,
                    sr_intent_list=SR_INTENT_LIST,
                    entity_super_list=ENTITY_SUPER_LIST,
                    phrase=phrase,
                )

                entity = sr_result["entity"]
                sr_flag = sr_result["sr_flag"]
                retry_flag = sr_result["retry_flag"]

                invalid_entity = sr_result["invalid_entity"]

                if invalid_entity:
                    response["response"] = language_data.get(
                        "error_message",
                        "Apologies, but I was unable to understand your request. "
                        "Kindly rephrase it for better assistance.",
                    )
                    response["loan_api_failure_flag"] = 0
                    response["type"] = "string"
                    response["retry_flag"] = "string"
                    if detected_mobile_no is None:
                        detected_mobile_no = ""

                    return {
                        "response": response,
                        "res_type": "string",
                        "status_code": 207,
                        "retry_flag": retry_flag,
                        "loan_api_failure_flag": 0,
                        "detected_mobile_no": detected_mobile_no,
                    }

                if entity in "loan_details_":
                    default_flag = sr_flag

            # ----------------------------------------------------------
            # Entity mapping
            # ----------------------------------------------------------
            if entity in ENTITY_LIMITED_LIST and agreement_number == "":
                resp, resp_count = await loan_details_based_on_agreement(
                    entity_loan_details,
                    query_input,
                    mobile_no,
                    detected_mobile_no,
                    agreement_number,
                    session_id,
                    logger,
                    redis_client,
                    redis_key_name,
                    entity,
                    show_all_loans,
                )
                logger.info(f"resp_count : {resp_count}")
                logger.info(f"resp api data : {resp}")
                if resp_count == 0:
                    loan_count = resp_count
                    api_resp = resp
                elif resp_count == 1:
                    loan_count = resp_count
                    if "identified_intent" not in resp:
                        api_resp = {}
                    else:
                        (
                            api_resp,
                            resp_count,
                            rem_flag,
                            loan_api_failure_flag,
                        ) = await entity_mapping(
                            resp["identified_intent"],
                            query_input,
                            mobile_no,
                            detected_mobile_no,
                            resp["agreement_number"],
                            session_id,
                            logger,
                            redis_client,
                            redis_key_name,
                            show_all_loans,
                        )
                else:
                    loan_count = resp_count
                    api_resp = resp
                    res_type = "json"
            else:
                (
                    api_resp,
                    resp_count,
                    rem_flag,
                    loan_api_failure_flag,
                ) = await entity_mapping(
                    entity,
                    query_input,
                    mobile_no,
                    detected_mobile_no,
                    agreement_number,
                    session_id,
                    logger,
                    redis_client,
                    redis_key_name,
                    show_all_loans,
                )
                loan_count = resp_count
                

        else:
            # show_more_req_flag != "0" — retrieve from Redis
            if redis_client is not None:
                api_resp, resp_count, rem_flag = retrieve_data_redis(
                    redis_client, redis_key_name, logger
                )

        logger.info(f"LOAN COUNT............ {resp_count}")
        logger.info(f"API RESPONSE........... {api_resp}")
        logger.info(f"FLAG........... {rem_flag}")

        if resp_count == 0 and loan_api_failure_flag == 0:
             
            api_resp["response"] = language_data.get(
                    "no_loan_message",
                    "No loans available under this mobile number"
                )


        if isinstance(api_resp, dict):
            if "response" not in api_resp:
                response["response"] = language_data.get(
                    "technical_error_message",
                    "We ran into a technical issue. Please try again later.",
                )
                status_code = 201
            else:
                if (
                    isinstance(api_resp["response"], list)
                    and len(api_resp["response"]) == 0
                ):
                    api_resp["response"] = language_data.get(
                            "no_loan_message",
                            "No loans available under this mobile number"
                        )


        if isinstance(api_resp, str):
            api_resp = json.loads(api_resp)

        logger.info(f"loan_count: {loan_count}")
        logger.info(f"api_resp: {api_resp}")
        logger.info(f"agreement_number: {agreement_number}")

        # ----------------------------------------------------------
        # Assign response["response"] from api_resp
        # Mirrors the raw file's multi-branch response assignment
        # ----------------------------------------------------------
        if isinstance(api_resp, list):
            response["response"] = api_resp

        elif (
            "identified_intent" in api_resp
            and api_resp["identified_intent"] in FLOW_RELATED
            and (loan_count != 0 or agreement_number != "")
        ):
            response["response"] = api_resp["identified_intent"]
            sr_flag = 1

        elif (
            "response" in api_resp
            and api_resp["response"] in FLOW_RELATED
            and (loan_count != 0 or agreement_number != "")
        ):
            response["response"] = api_resp["response"]
            sr_flag = 1

        elif (
            "result_text" in api_resp
            and api_resp["result_text"] in FLOW_RELATED
            and (loan_count != 0 or agreement_number != "")
        ):
            response["response"] = api_resp["result_text"]
            sr_flag = 1

        elif (
            "response" in api_resp
            and api_resp["response"] in ENTITY_SUPER_LIST
            and (loan_count != 0 or agreement_number != "")
        ):
            response["response"] = api_resp["response"]
            sr_flag = 1

        elif (
            "result_text" in api_resp
            and api_resp["result_text"] in ENTITY_SUPER_LIST
            and (loan_count != 0 or agreement_number != "")
        ):
            response["response"] = api_resp["result_text"]
            sr_flag = 1

        else:
            response["response"] = api_resp.get("response", "")
        res_type = "json" if not isinstance(response["response"], str) else "string"

        # ----------------------------------------------------------
        # Format entity response
        # Uses formatter_service for entities that need special
        # treatment; generic dict conversion for everything else.
        # ----------------------------------------------------------
        if (
            isinstance(response["response"], str)
            and response["response"] != "No Data Found"
            and entity not in NON_DICT_CONVERSION_ENTITIES
        ):

            # ------------------------------------------------------------------
            # CF05264 - no loan available issues
            # Skip dictionary conversion for plain text responses.
            # ------------------------------------------------------------------
            if (
                response["response"].strip().startswith("{")
                or response["response"].strip().startswith("[")
            ):
                try:
                    response["response"], res_type = convert_to_dict_if_possible(
                        response["response"], logger
                    )
                except Exception as e:
                    logger.error(
                        f"Error occurred while formatting entity response for {entity}: {e}"
                    )
                    api_resp["response"] = language_data.get(
                        "dict_conversion_message",
                        "We encountered an issue while processing the response. Please try again."
                    )
                    status_code = 202

            # ------------------------------------------------------------------
            # CF05264 - no loan available issues
            # Check object type before using .get().
            # ------------------------------------------------------------------
            try:
                if isinstance(response["response"], dict):
                    if (
                        response["response"].get("code") is not None
                        and response["response"]["code"] != 200
                    ):
                        response["response"] = response["response"]["message"]
                        res_type = "string"
            except Exception as e:
                logger.error(
                    f"Error occurred while formatting entity response for {entity}: {e}"
                )
                api_resp["response"] = language_data.get(
                    "code_response_message",
                    "We encountered an issue while processing the response. Please try again."
                )
                status_code = 204

        else:
            # Entities that bypass generic dict conversion go through
            # format_entity_response (formatter_service).
            try:
                formatted, fmt_res_type = format_entity_response(
                    entity,
                    response["response"],
                    agreement_number,
                    language_data,
                    logger
                    )
                response["response"] = formatted
                res_type = fmt_res_type
            except Exception as e:
                logger.error(f"Error occurred while formatting entity response for {entity}: {e}")
                response["response"] = language_data.get(
                    "fetch_error_message",
                    "Sorry! We are unable to fetch your details. Please try again later."
                )
                status_code = 209

        # ----------------------------------------------------------
        # Flag assembly (mirrors end of My Loans block in raw)
        # ----------------------------------------------------------
        if default_flag:
            sr_flag = 0

        response["counter_flag_agg"] = rem_flag
        response["sr_flag"] = sr_flag
        response["loan_count"] = loan_count

        if loan_count == 0 and len(agreement_number) == 0:
            response["apply_loan_flag"] = 1
            sr_flag = 0
            response["sr_flag"] = sr_flag

        if sr_flag == 1:
            response["sr_text"] = entity

        logger.info(f"responses : {response}")
        logger.info(f"response type : {type(response)}")

        res_type = "json" if not isinstance(response["response"], str) else "string"
        logger.info(f"res_type : {res_type}")
    return {
        "response": response,
        "res_type": res_type,
        "status_code": status_code,
        "retry_flag": retry_flag,
        "loan_api_failure_flag": loan_api_failure_flag,
        "detected_mobile_no": detected_mobile_no,
    }


# ---------------------------------------------------------------------------
# Utility: normalise loan API responses (used internally)
# ---------------------------------------------------------------------------

def build_loan_summary_response(api_resp, language_data):
    """
    Normalizes a raw loan API response dict into a response dict
    with a "response" key, handling empty / error cases.
    """

    response = {}

    if not api_resp:
        response["response"] = language_data.get(
            "technical_error_message",
            "We ran into a technical issue. Please try again later.",
        )
        return response

    if isinstance(api_resp, str):
        try:
            api_resp = json.loads(api_resp)
        except Exception:
            response["response"] = api_resp
            return response

    if isinstance(api_resp, list):
        response["response"] = api_resp
        return response

    if isinstance(api_resp, dict):
        if "response" not in api_resp:
            response["response"] = language_data.get(
                "technical_error_message",
                "We ran into a technical issue. Please try again later.",
            )
            return response

        if (
            isinstance(api_resp["response"], list)
            and len(api_resp["response"]) == 0
        ):
           api_resp["response"] = language_data.get(
                        "no_loan_message",
                        "No loans available under this mobile number"
                    )


        response["response"] = api_resp["response"]
        return response

    response["response"] = language_data.get(
        "technical_error_message",
        "We ran into a technical issue. Please try again later.",
    )
    return response