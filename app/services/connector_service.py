from __future__ import annotations

from typing import Optional
import re
import time
from fastapi import HTTPException
from app.schemas.pydantic_schema import QueryRequest, QueryResponse
from app.core.logging import *
from app.services.agent_connector import run_agent, filter_and_summarize, filter_leads, find_faq_answer
from app.services.payout_client import check_payout_status, capture_payout_query, check_lead_status


def _looks_like_name(message: str) -> bool:
    """
    Check if a message looks like it's just a person's name (no action keywords).
    Returns True if the message is 1-3 words, all alphabetic, and doesn't contain
    system keywords.
    """
    if not message or not message.strip():
        return False

    cleaned = message.strip()
    words = cleaned.split()

    # Names are typically 1-3 words
    if len(words) > 4:
        return False

    # All words should be alphabetic (names don't have numbers or special chars)
    if not all(w.isalpha() for w in words):
        return False

    # Should NOT contain system/action keywords
    keywords = {
        "show", "check", "status", "payout", "payouts", "lead", "leads",
        "loan", "loans", "pending", "paid", "failed", "my", "all",
        "help", "how", "what", "when", "where", "why", "who",
        "register", "submit", "track", "query", "complaint",
        "hello", "hi", "hey", "thanks", "thank", "ok", "okay", "yes", "no",
    }
    if any(w.lower() in keywords for w in words):
        return False

    # Each word should be at least 3 chars (avoid "hi", "ok", etc.)
    if any(len(w) < 3 for w in words):
        return False

    return True

async def process_connector_request(
    request: QueryRequest,
    credentials: HTTPBasicCredentials,
) -> QueryResponse:
    """
    Accept a natural language query from a vendor, route it to the appropriate
    payout API, and filter/summarize results based on the user's criteria.
    """
    st = time.time()

    # =========================================================
    # Logger setup — mirrors create_log_name() from the raw file
    # =========================================================
    dt, timestamp = create_log_name()
    log_file_name = f"{settings.LOGGER_PATH}connector_v1_{dt}.log"
    logger = setup_logger("connector_logger", log_file_name) 

    try:
        logger.info(f"User input : {request.message}")
        logger.info(f"User input : {request.vendor}")
        
        # Check for submit_lead intent first (before agent processing)
        message_lower = request.message.lower().strip()
        submit_lead_keywords = [
            "submit lead", "create lead", "add lead",
            "submit new lead", "new lead", "want to create lead",
            "want to submit lead", "i want to add a lead",
            "i want to submit a lead",
        ]
        
        for keyword in submit_lead_keywords:
            if keyword in message_lower:
                logger.info(f"Detected submit_lead intent: {request.message}")
                return QueryResponse(
                    intent="submit_lead",
                    message=None,
                    reasoning=None,
                    filters_applied=None,
                    filtered_response=None,
                    raw_api_response=None,
                )
        
        agent_result = run_agent(user_query=request.message, vendor=request.vendor, logger=logger)
        logger.info(f"Agent response : {agent_result}")
    except Exception as e:
        logger.exception(f"Exception in Agent response : {e}")
        raise HTTPException(status_code=500, detail=f"Agent processing failed: {e}")

    # If the agent needs clarification, return the message to the user
    # BUT first check if the input looks like a customer name — if so, try lead search
    if agent_result.action is None:
        if _looks_like_name(request.message):
            logger.info(f"Fallback: treating '{request.message}' as a name-based lead search")
            try:
                api_response = await check_lead_status(
                    connector_mobile=request.vendor,
                    status="All",
                    time_period_months=8,
                    limit=100,
                    offset=0,
                    vertical=request.vertical,
                    vendor_id=request.vendor_id,  # Pass vendor_id from request
                    logger=logger,
                )
                logger.info(f"Fallback lead status API response: {api_response}")

                filter_result = filter_leads(
                    api_response=api_response,
                    filters={"filter_name": request.message.strip()},
                    user_query=request.message,
                    logger=logger,
                )
                logger.info(f"Fallback lead filter result: {filter_result}")

                if filter_result["filtered_data"] is None:
                    return QueryResponse(
                        intent="check_lead_status",
                        message=filter_result["reasoning"],
                        reasoning=filter_result["reasoning"],
                        filters_applied={"filter_name": request.message.strip()},
                        filtered_response=None,
                        raw_api_response=api_response,
                    )

                return QueryResponse(
                    intent="check_lead_status",
                    message="Lead list retrieved and filtered successfully.",
                    reasoning=filter_result["reasoning"],
                    filters_applied={"filter_name": request.message.strip()},
                    filtered_response=filter_result["filtered_data"],
                    raw_api_response=api_response,
                )
            except Exception as e:
                logger.exception(f"Exception in fallback lead search: {e}")
                # Fall through to return the agent's clarification message

        return QueryResponse(
            intent=None,
            message=agent_result.message,
            reasoning=None,
            filters_applied=None,
            filtered_response=None,
            raw_api_response=None,
        )

    # Execute the appropriate API call based on the agent's decision
    try:
        if agent_result.action == "check_payout_status":
            api_response = await check_payout_status(
                vendor=agent_result.parameters["vendor"],
                date=agent_result.parameters["date"],
                vertical=request.vertical,
                logger=logger,
            )

            # Pass through the LLM to filter based on user criteria
            filter_result = filter_and_summarize(
                user_query=request.message,
                api_response=api_response,
                filters=agent_result.filters,
                logger=logger,
            )
            logger.info(f"Filter agent response : {filter_result}")

            # If filter returned no data (e.g., name not found), return the reasoning as message
            if filter_result["filtered_data"] is None:
                return QueryResponse(
                    intent="check_payout_status",
                    message=filter_result["reasoning"],
                    reasoning=filter_result["reasoning"],
                    filters_applied=agent_result.filters if agent_result.filters else None,
                    filtered_response=None,
                    raw_api_response=api_response,
                )

            return QueryResponse(
                intent="check_payout_status",
                message="Payout status retrieved and filtered successfully.",
                reasoning=filter_result["reasoning"],
                filters_applied=agent_result.filters if agent_result.filters else None,
                filtered_response=filter_result["filtered_data"],
                raw_api_response=api_response,
            )

        elif agent_result.action == "capture_payout_query":
            api_response = await capture_payout_query(
                vendor=agent_result.parameters["vendor"],
                query_type=agent_result.parameters["query_type"],
                query=agent_result.parameters["query"],
                vertical=request.vertical,
                logger=logger,
            )

            # Check if the API call failed
            if api_response and api_response.get("result") == "error":
                return QueryResponse(
                    intent="capture_payout_query",
                    message="We couldn't submit your query right now. Please try again later or call our helpdesk.",
                    reasoning=api_response.get("message"),
                    filters_applied=None,
                    filtered_response=None,
                    raw_api_response=api_response,
                )

            return QueryResponse(
                intent="capture_payout_query",
                message="Your query has been submitted successfully.",
                reasoning=None,
                filters_applied=None,
                filtered_response=None,
                raw_api_response=api_response,
            )

        elif agent_result.action == "check_lead_status":
            # Extract API params and filters
            connector_mobile = agent_result.parameters.get("connector_mobile", request.vendor)
            status = agent_result.parameters.get("status", "All")
            time_period_months = agent_result.parameters.get("time_period_months", 8)
            limit = agent_result.parameters.get("limit", 100)
            offset = agent_result.parameters.get("offset", 0)

            api_response = await check_lead_status(
                connector_mobile=connector_mobile,
                status=status,
                time_period_months=int(time_period_months),
                limit=100,
                offset=int(offset),
                vertical=request.vertical,
                vendor_id=request.vendor_id,  # Pass vendor_id from request
                logger=logger,
            )
            logger.info(f"Lead status API response: {api_response}")

            # Apply deterministic filters on the lead list
            filter_result = filter_leads(
                api_response=api_response,
                filters=agent_result.filters,
                user_query=request.message,
                logger=logger,
            )
            logger.info(f"Lead filter result: {filter_result}")

            # If filter returned no data (e.g., name not found)
            if filter_result["filtered_data"] is None:
                return QueryResponse(
                    intent="check_lead_status",
                    message=filter_result["reasoning"],
                    reasoning=filter_result["reasoning"],
                    filters_applied=agent_result.filters if agent_result.filters else None,
                    filtered_response=None,
                    raw_api_response=api_response,
                )

            return QueryResponse(
                intent="check_lead_status",
                message="Lead list retrieved and filtered successfully.",
                reasoning=filter_result["reasoning"],
                filters_applied=agent_result.filters if agent_result.filters else None,
                filtered_response=filter_result["filtered_data"],
                raw_api_response=api_response,
            )

        elif agent_result.action == "answer_faq":
            faq_result = find_faq_answer(
                question=agent_result.parameters.get("question", request.message),
                logger=logger,
            )
            logger.info(f"FAQ result: {faq_result}")
            return QueryResponse(
                intent="answer_faq",
                message=faq_result["answer"],
                answer=faq_result["answer"],
                reasoning=None,
                filters_applied=None,
                filtered_response=None,
                raw_api_response=None,
            )

        elif agent_result.action == "submit_lead":
            # Simple return for submit_lead intent
            logger.info(f"Submit lead intent detected")
            return QueryResponse(
                intent="submit_lead",
                message=None,
                reasoning=None,
                filters_applied=None,
                filtered_response=None,
                raw_api_response=None,
            )

        else:
            logger.error(f"Unknown action from agent: {agent_result.action}")
            raise HTTPException(
                status_code=400,
                detail=f"Unknown action: {agent_result.action}",
            )


    except Exception as e:
        logger.exception(f"Exception in Upstream API response : {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Upstream API call failed: {e}",
        )
