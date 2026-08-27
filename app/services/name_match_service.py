# app/services/name_match_service.py
import time
from difflib import SequenceMatcher
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials
from app.core.logging import *
from app.core.config import settings
from app.schemas.pydantic_schema import NameMatchRequest, NameMatchResponse


def normalize_name(name: str) -> str:
    """
    Normalize a name by converting to lowercase and removing extra spaces.
    
    Args:
        name (str): The name to normalize
        
    Returns:
        str: Normalized name
    """
    if not isinstance(name, str):
        return ""
    return name.strip().lower()


def calculate_name_similarity(name1: str, name2: str) -> float:
    """
    Calculate the similarity ratio between two names using SequenceMatcher.
    
    Args:
        name1 (str): First name to compare
        name2 (str): Second name to compare
        
    Returns:
        float: Similarity ratio between 0.0 and 1.0
    """
    normalized_name1 = normalize_name(name1)
    normalized_name2 = normalize_name(name2)
    
    if not normalized_name1 or not normalized_name2:
        return 0.0
    
    matcher = SequenceMatcher(None, normalized_name1, normalized_name2)
    return matcher.ratio()


async def match_names(
    request: NameMatchRequest,
    credentials: HTTPBasicCredentials,
) -> NameMatchResponse:
    """
    Compare PAN name and Aadhar name and return match status.
    
    Args:
        pan_name (str): Name from PAN document
        aadhar_name (str): Name from Aadhar document
        threshold (float): Similarity threshold (default: 0.7 or 70%)
        
    Returns:
        Dict: Contains:
            - matched_flag (bool): True if similarity >= threshold, False otherwise
            - similarity_score (float): The calculated similarity ratio
            - pan_name_normalized (str): Normalized PAN name
            - aadhar_name_normalized (str): Normalized Aadhar name
    """
    st = time.time()

    # =========================================================
    # Logger setup — mirrors create_log_name() from the raw file
    # =========================================================
    dt, timestamp = create_log_name()
    log_file_name = f"{settings.LOGGER_PATH}name_match_v1_{dt}.log"
    logger = setup_logger("name_match_logger", log_file_name) 
    try:
        # Calculate similarity
        pan_name = request.pan_name
        aadhar_name = request.aadhar_name
        threshold = request.threshold
        logger.info(f"User input : {pan_name}")
        logger.info(f"User input : {aadhar_name}")
        logger.info(f"User input : {threshold}")
        similarity_score = calculate_name_similarity(pan_name, aadhar_name)
        
        # Determine if match is successful
        matched_flag = similarity_score >= threshold
        logger.info("Matched flag:", {matched_flag})
        return {
            "matched_flag": matched_flag,
            "similarity_score": round(similarity_score, 4),
            "pan_name_normalized": normalize_name(pan_name),
            "aadhar_name_normalized": normalize_name(aadhar_name),
        }
    
    except Exception as e:
        logger.exception("Exception in name match:", {e})
        return {
            "matched_flag": False,
            "similarity_score": 0.0,
            "pan_name_normalized": "",
            "aadhar_name_normalized": "",
            "error": str(e),
        }
