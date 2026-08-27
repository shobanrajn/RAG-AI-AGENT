import httpx
import certifi
from app.core.config import settings
from typing import Literal

# SSL/TLS certificate verification is handled via verify=certifi.where() parameter

# Valid verticals
VALID_VERTICALS = ["LAP", "HL", "SME"]


def get_api_config(vertical: str = "LAP") -> dict:
    """
    Get API configuration (complete URL and API key) for a given vertical.
    
    Args:
        vertical: Vertical identifier (LAP, HL, SME). Defaults to LAP.
        
    Returns:
        Dictionary containing payout_status_url and api_key for the vertical.
        
    Raises:
        ValueError: If vertical is not recognized.
    """
    vertical = vertical.upper() if vertical else "LAP"
    
    if vertical not in VALID_VERTICALS:
        raise ValueError(f"Invalid vertical: {vertical}. Must be one of {VALID_VERTICALS}")
    
    try:
        # Get the complete payout status URL (not base URL)
        payout_status_url = getattr(settings, f"PAYOUT_API_BASE_URL_{vertical}")
        api_key = getattr(settings, f"PAYOUT_API_KEY_{vertical}")
        return {
            "payout_status_url": payout_status_url,
            "api_key": api_key,
        }
    except Exception as e:
        raise RuntimeError(f"Failed to load API config for vertical {vertical}: {e}")


def get_lead_api_config(vertical: str = "LAP") -> dict:
    """
    Get Lead Status API configuration for a given vertical.
    
    Args:
        vertical: Vertical identifier (LAP, HL, SME). Defaults to LAP.
        
    Returns:
        Dictionary containing lead_status_base_url and lead_status_api_key for the vertical.
        
    Raises:
        ValueError: If vertical is not recognized.
    """
    vertical = vertical.upper() if vertical else "LAP"
    
    if vertical not in VALID_VERTICALS:
        raise ValueError(f"Invalid vertical: {vertical}. Must be one of {VALID_VERTICALS}")
    
    try:
        base_url = getattr(settings, f"LEAD_STATUS_API_BASE_URL_{vertical}")
        api_key = getattr(settings, f"LEAD_STATUS_API_KEY_{vertical}")
        return {
            "lead_status_base_url": base_url,
            "lead_status_api_key": api_key,
        }
    except Exception as e:
        raise RuntimeError(f"Failed to load Lead API config for vertical {vertical}: {e}")


def _build_lead_status_payload(
    connector_mobile: str,
    status: str,
    time_period_months: int,
    limit: int,
    offset: int,
    vertical: str,
    vendor_id: str = None,
) -> dict:
    """
    Build the lead status API payload based on the vertical.
    
    Different verticals have different API input requirements:
    - LAP: Uses connector_mobile field + filtering parameters
    - HL: Uses mobile_number and vendor_id fields (mobile_number from connector_mobile, vendor_id from input)
    - SME: Uses connector_mobile field + filtering parameters (same as LAP)
    
    Note:
    - "vendor" in the input refers to the connector's mobile number
    - "vendor_id" is a separate field passed in the input payload (for HL API)
    - The same mobile number is used across all verticals but formatted differently:
      * LAP/SME: Sent as "connector_mobile" field with filtering parameters
      * HL: Sent as "mobile_number" (numeric from connector_mobile) and "vendor_id" (from input)
    
    Args:
        connector_mobile: The connector's mobile number (10 digits, comes from "vendor" field).
        status: Lead status filter.
        time_period_months: Number of months to look back.
        limit: Fixed limit value (always 100).
        offset: Pagination offset.
        vertical: Product vertical (LAP, HL, SME).
        vendor_id: Vendor identifier (required for HL API, from input payload).
        
    Returns:
        Dictionary containing the API payload formatted for the specific vertical.
    """
    vertical = vertical.upper() if vertical else "LAP"
    
    if vertical == "HL":
        # HL API requires:
        # - mobile_number: connector's mobile number (numeric, from vendor/connector_mobile)
        # - vendor_id: vendor identifier (separate field from input payload)
        if not vendor_id:
            raise ValueError("vendor_id is required for HL vertical")
        return {
            "mobile_number": int(connector_mobile),  # HL expects numeric mobile_number
            "vendor_id": vendor_id,                  # HL expects vendor_id from input payload
        }
    elif vertical in ["LAP", "SME"]:
        # LAP and SME use the same payload structure with connector_mobile and filtering parameters
        return {
            "connector_mobile": connector_mobile,
            "status": status,
            "time_period_months": time_period_months,
            "limit": limit,
            "offset": offset,
        }
    else:
        raise ValueError(f"Unknown vertical: {vertical}")


async def check_payout_status(vendor: str, date: str, vertical: str = "LAP", logger=None) -> dict:
    """
    Call the Payout Status API for a specific vertical.

    Args:
        vendor: Vendor mobile number or ID (10 digits).
        date: Month in YYYY-MM format.
        vertical: Product vertical (LAP, HL, SME). Defaults to LAP.
        logger: Logger instance.

    Returns:
        API response as a dictionary.
    """
    try:
        api_config = get_api_config(vertical)
        url = api_config['payout_status_url']
        headers = {
            "x-api-key": api_config['api_key'],
            "Content-Type": "application/json",
        }
        payload = {"vendor": vendor, "date": date}

        if logger:
            logger.info(f"Check payout API payload (vertical: {vertical}): {payload}")
        
        async with httpx.AsyncClient(verify=certifi.where(), timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
        
        if logger:
            logger.info(f"Check payout API response status code: {response.status_code}")
        
        # Check if status code is not 200
        if response.status_code != 200:
            if logger:
                logger.error(f"Payout API returned status code {response.status_code} (vertical: {vertical})")
            return {
                "result": "error", 
                "message": "Currently, unable to fetch the data. Please try again later.",
                "agreements": []
            }
        
        response.raise_for_status()
        
        data = response.json()
        if logger:
            logger.info(f"Check payout API response: {data}")
        
        # Check for specific "no_agreements_found" error
        if data.get("result") == "error" and data.get("error_message") == "no_agreements_found":
            if logger:
                logger.info(f"No agreements found for vendor {vendor} in {date} (vertical: {vertical})")
            return {"result": "success", "message": "No agreements found", "agreements": []}
        
        # If response explicitly has a "result" key with "error" value (other errors), it's an error
        if data.get("result") == "error":
            if logger:
                logger.info(f"API returned error: {data.get('error_message') or data.get('message')}")
            return data
        
        # If the response has agreements, return it as-is (success case)
        if data.get("agreements"):
            if logger:
                logger.info(f"Payout data found for vendor {vendor} in {date} (vertical: {vertical})")
            return data
        
        # If no agreements found, return success with empty data instead of error
        if logger:
            logger.info(f"No payout data found for vendor {vendor} in {date} (vertical: {vertical})")
        return {"result": "success", "message": "No agreements found", "agreements": []}
        
    except ValueError as e:
        if logger:
            logger.error(f"Invalid vertical specified: {e}")
        return {"result": "error", "message": str(e), "agreements": []}
    except Exception as e:
        if logger:
            logger.exception(f"Exception in check payout API response: {e}")
        return {"result": "error", "message": str(e), "agreements": []}


async def capture_payout_query(vendor: str, query_type: str, query: str, vertical: str = "LAP", logger=None) -> dict:
    """
    Call the Payout Query API to log a vendor's query/complaint for a specific vertical.

    Args:
        vendor: Vendor mobile number or ID (10 digits).
        query_type: Category of query (Payment Delay, Amount Mismatch, Missing Payment, Other).
        query: The actual query text from the vendor.
        vertical: Product vertical (LAP, HL, SME). Defaults to LAP.
        logger: Logger instance.

    Returns:
        API response as a dictionary.
    """
    try:
        api_config = get_api_config(vertical)
        # Construct the payout query endpoint from the base payout status URL
        base_url = api_config['payout_status_url']
        # Replace "get-payout-status" with "get-payout-query" if it exists, otherwise append
        if base_url.endswith('/get-payout-status'):
            url = base_url.replace('/get-payout-status', '/get-payout-query')
        else:
            url = f"{base_url.rstrip('/')}/get-payout-query"
        
        headers = {
            "x-api-key": api_config['api_key'],
            "Content-Type": "application/json",
        }
        payload = {"vendor": vendor, "query_type": query_type, "query": query}

        async with httpx.AsyncClient(verify=certifi.where(), timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
        
        if logger:
            logger.info(f"Capture payout API query response (vertical: {vertical}): {response}")
            logger.info(f"Capture payout API response status code: {response.status_code}")
        
        # Check if status code is not 200
        if response.status_code != 200:
            if logger:
                logger.error(f"Capture payout API returned status code {response.status_code} (vertical: {vertical})")
            return {
                "result": "error",
                "message": "Currently, unable to fetch the data. Please try again later."
            }
        
        response.raise_for_status()
        return response.json()
    except ValueError as e:
        if logger:
            logger.error(f"Invalid vertical specified: {e}")
        return {"result": "error", "message": str(e)}
    except Exception as e:
        if logger:
            logger.exception(f"Exception in capture payout API response: {e}")
        return {"result": "error", "message": str(e)}
    


async def check_lead_status(
    connector_mobile: str,
    status: str = "All",
    time_period_months: int = 1,
    limit: int = None,
    offset: int = 0,
    vertical: str = "LAP",
    vendor_id: str = None,
    logger=None,
) -> dict:
    """
    Call the Lead Status API to fetch leads submitted by a connector for a specific vertical.
    
    The payload structure varies by vertical:
    - LAP/SME: Uses connector_mobile, status, time_period_months, limit, offset
    - HL: Uses mobile_number (from connector_mobile), vendor_id (from input)

    Args:
        connector_mobile: The connector's mobile number (10 digits).
        status: Lead status filter (All, Submitted, Under Review, Sanctioned, Rejected, Disbursed).
        time_period_months: Number of months to look back.
        limit: Number of records to fetch (ignored, always uses 100).
        offset: Pagination offset.
        vertical: Product vertical (LAP, HL, SME). Defaults to LAP.
        vendor_id: Vendor identifier (required for HL vertical).
        logger: Logger instance.

    Returns:
        API response as a dictionary.
    """
    # Always use limit of 100 - never assume any other numbers
    FIXED_LIMIT = 100
    
    try:
        vertical = vertical.upper() if vertical else "LAP"
        lead_config = get_lead_api_config(vertical)
        url = lead_config['lead_status_base_url']
        headers = {
            "x-api-key": lead_config['lead_status_api_key'],
            "Content-Type": "application/json",
        }
        
        # Build payload based on vertical requirements
        payload = _build_lead_status_payload(
            connector_mobile=connector_mobile,
            status=status,
            time_period_months=time_period_months,
            limit=FIXED_LIMIT,
            offset=offset,
            vertical=vertical,
            vendor_id=vendor_id,
        )

        if logger:
            logger.info(f"Check lead status API URL (vertical: {vertical}): {url}")
            logger.info(f"Check lead status API payload (vertical: {vertical}): {payload}")

        async with httpx.AsyncClient(verify=certifi.where(), timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
        
        if logger:
            logger.info(f"Check lead status API response status (vertical: {vertical}): {response.status_code}")
        
        # Check if status code is not 200
        if response.status_code != 200:
            if logger:
                logger.error(f"Lead status API returned status code {response.status_code} (vertical: {vertical})")
            return {
                "result": "error",
                "message": "Currently, unable to fetch the data. Please try again later.",
                "leads": []
            }
        
        response.raise_for_status()
        
        data = response.json()
        if logger:
            logger.info(f"Check lead status API response (vertical: {vertical}): {data}")
        
        # If response is successful but has no data, don't treat as error
        if data.get("result") == "error":
            if logger:
                logger.info(f"API returned error: {data.get('message')}")
            return data
        
        # Extract leads from different possible response structures
        # HL API: data.data.leads
        # LAP API: data.result.leads or data.leads
        if isinstance(data.get("result"), dict):
            leads = data.get("result", {}).get("leads") 
        elif isinstance(data.get("data"), dict):
            leads = data.get("data", {}).get("leads")  
        else:
            leads = data.get("leads")
        
        if logger:
            logger.info(f"Leads found: {leads}")
        
        if not leads:
            if logger:
                logger.info(f"No leads found for connector {connector_mobile} (vertical: {vertical})")
            return {"result": "success", "message": "No leads found", "leads": []}
        
        # Normalize response structure for consistent handling by filter_leads()
        # Convert to standard format: {"result": {"leads": [...]}}
        normalized_response = {
            "result": {
                "leads": leads
            }
        }
        
        return normalized_response
    except ValueError as e:
        if logger:
            logger.error(f"Validation error: {e}")
        return {"result": "error", "message": str(e), "leads": []}
    except Exception as e:
        if logger:
            logger.exception(f"Exception in check lead status API: {e}")
        return {"result": "error", "message": str(e), "leads": []}
