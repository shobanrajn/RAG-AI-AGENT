from __future__ import annotations

import re
import json
import hashlib
from difflib import SequenceMatcher
from datetime import datetime, timedelta
import boto3
from typing import Optional
from app.core.config import settings
from app.services.prompt_cache import get_prompt_cache_manager


bedrock_client = boto3.client("bedrock-runtime", region_name=settings.AWS_DEFAULT_REGION)
prompt_cache_manager = None  # Lazy-initialized on first use

SYSTEM_PROMPT = """You are an intelligent assistant for a payout system. Your job is to understand the user's query and determine which action to take.

You have access to four tools:

1. **check_payout_status** - Use this when the user wants to check the status of their payout/payment for a specific month.
   IMPORTANT: The vendor's mobile number is already provided in the context above. Use it automatically — do NOT ask the user for it.
   Required parameters:
   - vendor: The vendor's mobile number or ID (10 digits) — use the vendor's mobile number from the context provided above
   - date: The month and year in "YYYY-MM" format
   Optional filter parameters (extract these from the user's query if mentioned):
   - filter_status: Filter by payout status (e.g., "Pending", "Paid", "Failed")
   - filter_name: Filter by customer/borrower name
   - filter_date: Filter by specific date within the month (e.g., "2026-01-15")
   - filter_loan_amount: Filter by loan amount (exact value or range like ">50000", "<100000")
   - filter_payout: Filter by payout amount (exact value or range like ">300", "<5000")

2. **capture_payout_query** - Use this when the user has a question, complaint, or issue about their payout that needs to be logged/raised.
   IMPORTANT: The vendor's mobile number is already provided in the context above. Use it automatically — do NOT ask the user for it.
   Required parameters:
   - vendor: The vendor's mobile number or ID (10 digits) — use the vendor's mobile number from the context provided above
   - query_type: One of "Payment Delay", "Amount Mismatch", "Missing Payment", "Other"
   - query: The actual query or complaint text from the vendor

3. **check_lead_status** - Use this when the user wants to see their leads, lead list, lead status, or track submitted leads.
   IMPORTANT: The connector's mobile number (vendor) is already provided in the context above. Use it automatically — do NOT ask the user for it.
   Required parameters:
   - connector_mobile: The connector's mobile number (10 digits) — use the vendor's mobile number from the context provided above
   Optional parameters:
   - status: Filter by lead status (e.g., "All", "Submitted", "Under Review", "Sanctioned", "Rejected", "Disbursed"). Default "All".
   - time_period_months: How many months back to look (default 8)
   - limit: Number of records to fetch (default 10)
   - offset: Pagination offset (default 0)
   Optional filter parameters (extract from user's query if mentioned):
   - filter_name: Filter by customer/lead name
   - filter_mobile: Filter by customer's mobile number
   - filter_loan_amount: Filter by loan amount (exact or range like ">500000", "<1000000")
   - filter_status: Filter by specific lead status. ONLY use if user mentions one of these exact keywords: "Login", "In Progress", "Disbursed", "Rejected", "Lead Closed"

4. **answer_faq** - Use this when the user asks a general/informational question about the Chola One Partners program, registration, lead submission, lead stages, payout rates, loyalty tiers, documents, eligibility, privacy, or any other program-related query that does NOT require fetching live data or logging a complaint.
   Required parameters:
   - question: The user's question rephrased clearly (keep it close to original wording)

Guidelines:
- If the user mentions checking payout status, payment status, or wants to know if they got paid for a specific month — use check_payout_status.
- If the user simply says "payout", "show payout", "my payout", or "payout status" WITHOUT specifying a month, use check_payout_status with the CURRENT month as the date. Do NOT ask for clarification — default to current month.
- If the user mentions "my leads", "lead list", "lead status", "show leads", "track lead", "submitted leads", or wants to see the list of leads they have submitted — use check_lead_status.
- CRITICAL NAME-ONLY QUERY RULE: If the user's entire message is JUST a name (one or two words that look like a person's name, e.g., "bablu", "suresh kumar", "jayabrata"), treat it as a check_lead_status request with that name as filter_name. The user is asking to search for that customer in their leads.
  * Examples: "bablu" → check_lead_status with filter_name: "bablu". "suresh" → check_lead_status with filter_name: "suresh". "BUBUL KALITA" → check_lead_status with filter_name: "BUBUL KALITA".
  * How to identify: The message contains NO action words (no "show", "check", "status", "payout", "lead", "loan", etc.) and is just 1-3 words that look like a person's name.
- If the user is raising a complaint, asking why something happened, or reporting an issue — use capture_payout_query.
- If the user asks a general/informational question (e.g., "how do I register?", "what is my payout rate?", "what documents do I need?", "what are the lead stages?", "what is Chola One Partners?", "how do I submit a lead?", "what are the loyalty tiers?", "what is the helpdesk number?") — use answer_faq.
- If you cannot determine the vendor number or date from the query, ask the user for the missing information.
- Always extract parameters from the user's message when possible.
- For dates, interpret relative references (e.g., "last month", "January") relative to the current date provided below.
- CRITICAL DATE RULES:
  - "last month" or "previous month" = the month immediately before the current month based on today's date.
  - If only a month name is mentioned (e.g., "January", "March") WITHOUT a year, assume the CURRENT YEAR.
  - If both month and year are mentioned explicitly (e.g., "March 2025", "Jan 2024"), use both as given.
  - Always output the date in "YYYY-MM" format.
- IMPORTANT: If the user asks for specific filtering (e.g., "only pending", "show paid ones", "for customer Ravi", "loans above 50000", "payout greater than 300"), extract those as filter parameters.
- CRITICAL FILTER IDENTIFICATION RULES — carefully read the user's message and pick the correct filter:
  - filter_loan_amount: Use when the user mentions "loan amount", "loan", "loan value", "loan greater/less than", "loans above/below". Keywords: loan, loan amount, loan value. Examples: "show loans > 300" = filter_loan_amount: ">300", "loans < 500000" = filter_loan_amount: "<500000"
  - filter_payout: Use when the user mentions "payout", "payout amount", "earning", "commission", "payout greater/less than". Keywords: payout, earning, commission. Examples: "show payout > 300" = filter_payout: ">300", "earnings < 5000" = filter_payout: "<5000"
  - filter_status (for check_lead_status ONLY): Use ONLY when user explicitly mentions one of these exact keywords: "Login", "In Progress", "Disbursed", "Rejected", "Lead Closed". NEVER extract filter_status if user mentions any other status value. If user mentions any other status not in this list, ignore it and do NOT set filter_status.
    * CRITICAL - LEAD STATUS KEYWORD UNDERSTANDING: The system maintains a mapping between user-friendly keywords and actual lead status groups. You MUST understand and match user input to these groups:
      - "Login" → Maps to lead show_status: ["Login"]
      - "In Progress" → Maps to lead show_status: ["Docs Collections In Process", "In Progress", "Interested", "Unable To Connect", "Follow-up Required"]
      - "Disbursed" → Maps to lead show_status: ["In Disbursal Stage"]
      - "Rejected" → Maps to lead show_status: ["Rejected", "Cancelled"]
      - "Lead Closed" → Maps to lead show_status: ["Not Interested", "Not Eligible", "Interested In Other Product"]
    * When user mentions any status-related words or shows interest in a specific lead stage, map it to ONE of the above five groups. For example:
      - User says "show me leads interested in the product" → This relates to "In Progress" (includes "Interested")
      - User says "show leads that are cancelled" → This relates to "Rejected" (includes "Cancelled")
      - User says "show not interested leads" → This relates to "Lead Closed" (includes "Not Interested")
      - User says "leads in disbursal" → This relates to "Disbursed" (includes "In Disbursal Stage")
      - User says "show login stage leads" → This relates to "Login"
    * Extract ONLY ONE of these five keywords based on the user's intent. If the user's query doesn't clearly match any of these groups, do NOT set filter_status.
  - filter_status (for check_payout_status): Use when the user mentions "pending", "paid", "failed", "unpaid", "status". Keywords: pending, paid, failed, status.
  - filter_name: Use when the user mentions a person's name or "customer name", "borrower name", "for customer X". Keywords: customer, name, borrower, or any proper noun that looks like a person's name.
    * CRITICAL NAME DETECTION: If ANY word in the query looks like a person's name (proper noun, not a system keyword), ALWAYS extract it as filter_name. Even if it appears alongside "lead", "leads", "payout", "status", etc.
    * Examples: "show me bablu lead" → filter_name: "bablu". "ramesh ka status" → filter_name: "ramesh". "lead of suresh kumar" → filter_name: "suresh kumar". "bablu sarkar ka lead dikhao" → filter_name: "bablu sarkar".
    * The name may be a first name only, a last name only, or a full name. Extract whatever name part the user provides.
    * If the user says "show me <name> lead/leads/payout/status", the word before "lead/leads/payout/status" is likely a person's name — extract it as filter_name.
    * Common patterns: "<name> ka lead", "<name> lead dikhao", "show <name>", "<name> status", "details of <name>", "<name> ka payout".
  - filter_mobile: Use when the user mentions a 10-digit mobile number to filter by (for check_lead_status).
  - MOST CRITICAL - Number Extraction Rules:
    * If the user says "show loans greater than 300", extract ">300" (NOT ">300000")
    * If the user says "show payouts less than 500", extract "<500" (NOT "<500000")
    * If the user says "loans 3 lakhs" or "3L", convert to ">300000" (Indian unit conversion)
    * If the user says "loans with amount 500", extract "500" (exact match, no operator)
    * If the user says "loans 3000000", extract "3000000" (exact match)
    * NEVER assume the user meant to scale the number. Trust their literal input.
- CRITICAL: These filter rules apply to BOTH check_payout_status AND check_lead_status. Always extract filter parameters when the user mentions any filtering criteria alongside a lead or payout query.
- CRITICAL for loan amount and payout filters: Use the EXACT number the user mentions. Do NOT add zeros, scale, or convert units. If the user says "greater than 300", the filter value must be ">300", NOT ">300000" or ">3,00,000". Pass the user's number verbatim with only the operator prefix. If no operator is mentioned (just a number), pass the number as-is for exact match.
  - MANDATORY RULE: If the user says a plain number like "300" or "500" or "5000" WITHOUT units, it MUST stay exactly as-is. Do NOT add zeros, do NOT convert to lakhs/crore, do NOT assume they meant something else.
  - MANDATORY EXAMPLES - You MUST follow these exactly:
    * User: "show loans less than 300" → filter_loan_amount: "<300" (EXACTLY 300, NOT 300000 or 3,00,000)
    * User: "show loans greater than 300" → filter_loan_amount: ">300" (EXACTLY 300, NOT 300000)
    * User: "show loans above 50000" → filter_loan_amount: ">50000" (EXACTLY 50000 as the user said)
    * User: "show payout less than 500" → filter_payout: "<500" (EXACTLY 500, NOT 500000)
    * User: "leads with loan 2500000" → filter_loan_amount: "2500000" (EXACTLY as user typed)
  - IF user includes units (ONLY THEN convert): "3 lakhs" = 300000, "5 crore" = 50000000, "2.5L" = 250000, "50k" = 50000. But if NO unit word, the number stays as-is.
  - FILTER EXTRACTION RULE: Look at the user's exact text. Count the digits. If they say "300", there are 3 digits. Your output must have 3 digits unless they explicitly said "lakh" or "crore" or "k" or "L".
- OPERATOR RULES: Use ">" for "greater than/above/more than", "<" for "less than/below/under", ">=" for "at least/minimum", "<=" for "at most/maximum". If NO operator word is used and just a number is given, pass it as-is (exact match). Always use the plain ASCII characters > and < (never HTML entities).
"""

TOOLS = [
    {
        "toolSpec": {
            "name": "check_payout_status",
            "description": "Check the payout status for a vendor for a specific month, with optional filters for status, name, date, and loan amount",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "vendor": {
                            "type": "string",
                            "description": "The vendor's mobile number or ID (10 digits)",
                        },
                        "date": {
                            "type": "string",
                            "description": "The month to check in YYYY-MM format (e.g., 2026-01)",
                        },
                        "filter_status": {
                            "type": "string",
                            "description": "Filter by payout status. Use when user mentions 'pending', 'paid', 'failed', or 'status'. Values: Pending, Paid, Failed.",
                        },
                        "filter_name": {
                            "type": "string",
                            "description": "Filter by customer/borrower name. Use when user mentions a person's name or says 'for customer X'. Partial match supported.",
                        },
                        "filter_date": {
                            "type": "string",
                            "description": "Filter by specific date within the month (YYYY-MM-DD format). Use when user asks for a specific day.",
                        },
                        "filter_loan_amount": {
                            "type": "string",
                            "description": "Filter by LOAN amount. Use ONLY when user explicitly mentions 'loan', 'loan amount', or 'loan value'. Use EXACT number from user — do NOT scale, do NOT add zeros, do NOT assume units. If user says '>300', use '>300' literally (NOT '>300000'). If user says a number with Indian units (e.g., '3 lakhs'), convert to plain number ('300000'). But if user says plain '300' with NO unit, keep as '300'. Examples: '>200000', '<500000', '100000'.",
                        },
                        "filter_payout": {
                            "type": "string",
                            "description": "Filter by PAYOUT/earning amount. Use ONLY when user explicitly mentions 'payout', 'earning', or 'commission'. Use EXACT number from user — do NOT scale, do NOT add zeros, do NOT assume units. If user says '>300', use '>300' literally (NOT '>300000'). Examples: '>300', '<5000', '1000-5000'.",
                        },
                    },
                    "required": ["vendor", "date"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "capture_payout_query",
            "description": "Capture and log a payout-related query or complaint from a vendor",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "vendor": {
                            "type": "string",
                            "description": "The vendor's mobile number or ID (10 digits)",
                        },
                        "query_type": {
                            "type": "string",
                            "enum": [
                                "Payment Delay",
                                "Amount Mismatch",
                                "Missing Payment",
                                "Other",
                            ],
                            "description": "The category of the query",
                        },
                        "query": {
                            "type": "string",
                            "description": "The actual query or complaint text",
                        },
                    },
                    "required": ["vendor", "query_type", "query"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "check_lead_status",
            "description": "Fetch the list of leads submitted by a connector, with optional filters for status, name, mobile number, and loan amount",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "connector_mobile": {
                            "type": "string",
                            "description": "The connector's mobile number (10 digits)",
                        },
                        "status": {
                            "type": "string",
                            "description": "Lead status filter. Values: All, Submitted, Under Review, Sanctioned, Rejected, Disbursed. Default: All.",
                        },
                        "time_period_months": {
                            "type": "number",
                            "description": "Number of months to look back. Default: 8.",
                        },
                        "limit": {
                            "type": "number",
                            "description": "Number of records to fetch. FIXED: Always 100. This parameter is ignored and 100 records will always be fetched.",
                        },
                        "offset": {
                            "type": "number",
                            "description": "Pagination offset. Default: 0.",
                        },
                        "filter_name": {
                            "type": "string",
                            "description": "Filter leads by customer name. Use when user mentions a person's name.",
                        },
                        "filter_mobile": {
                            "type": "string",
                            "description": "Filter leads by customer's mobile number.",
                        },
                        "filter_loan_amount": {
                            "type": "string",
                            "description": "Filter by loan amount. Use EXACT number from user input. Do NOT scale, do NOT add zeros, do NOT assume units. If user says '>300', keep as '>300' (NOT '>300000'). If user mentions Indian units (e.g., '3 lakhs'), convert to plain number ('300000'). Examples: '>500000', '<1000000', '500000-1000000'.",
                        },
                        "filter_status": {
                            "type": "string",
                            "description": "Filter by lead status after fetching. Use ONLY when user mentions one of these exact keywords: 'Login', 'In Progress', 'Disbursed', 'Rejected', 'Lead Closed'. Only extract this if user's query explicitly mentions one of these statuses.",
                        },
                    },
                    "required": ["connector_mobile"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "answer_faq",
            "description": "Answer a general informational question about Chola One Partners program including registration, lead submission, lead stages, payout rates, loyalty tiers, documents needed, eligibility, privacy, RM queries, or any other program-related FAQ",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "The user's question rephrased clearly, keeping close to original wording",
                        },
                    },
                    "required": ["question"],
                }
            },
        }
    },
]


class AgentResponse:
    """Represents the agent's decision after processing a user query."""

    def __init__(
        self,
        action=None,
        parameters=None,
        message=None,
        filters=None,
    ):
        self.action = action  # "check_payout_status" or "capture_payout_query" or None
        self.parameters = parameters or {}
        self.message = message  # Follow-up message or filtered response
        self.filters = filters or {}  # Extracted filter criteria


def _convert_indian_units(number_str: str, unit: str) -> str:
    """
    Convert Indian unit words (lakh, crore, thousand, etc.) to plain numbers.
    E.g., "3 lakhs" -> "300000", "2.5 crore" -> "25000000", "5L" -> "500000"
    """
    unit = unit.lower().strip().rstrip("s")  # normalize: "lakhs" -> "lakh"
    
    multipliers = {
        "lakh": 100000,
        "lac": 100000,
        "l": 100000,
        "crore": 10000000,
        "cr": 10000000,
        "c": 10000000,
        "thousand": 1000,
        "k": 1000,
        "million": 1000000,
        "m": 1000000,
    }

    multiplier = multipliers.get(unit, 1)
    try:
        base_number = float(number_str.replace(",", ""))
        result = base_number * multiplier
        # Return as integer string if it's a whole number
        if result == int(result):
            return str(int(result))
        return str(result)
    except ValueError:
        return number_str


def _extract_date_from_query(user_query: str, current_date: datetime = None) -> str:
    """
    Extract date from user query and convert to YYYY-MM format.
    If no date is mentioned, default to January 2026 (2026-01).
    
    Handles:
    - Relative dates: "last month", "previous month", "current month"
    - Month names: "January", "March", "Dec 2025"
    - Full dates: "January 2026", "2026-01", "01/2026"
    - No date mention: defaults to "2026-01"
    
    Args:
        user_query: The natural language query from the user.
        current_date: Optional current date for relative calculations (defaults to today).
    
    Returns:
        Date string in YYYY-MM format.
    """
    if current_date is None:
        current_date = datetime.now()
    
    query_lower = user_query.lower()
    
    # Month name mapping
    month_names = {
        "january": 1, "jan": 1, "februar": 2, "feb": 2, "march": 3, "mar": 3,
        "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
        "august": 8, "aug": 8, "september": 9, "sep": 9, "october": 10, "oct": 10,
        "november": 11, "nov": 11, "december": 12, "dec": 12
    }
    
    # Check for relative date references
    if "last month" in query_lower or "previous month" in query_lower:
        target_date = current_date.replace(day=1) - timedelta(days=1)
        return target_date.strftime("%Y-%m")
    
    if "current month" in query_lower or "this month" in query_lower:
        return current_date.strftime("%Y-%m")
    
    # Check for explicit month name with optional year
    for month_name, month_num in month_names.items():
        if month_name in query_lower:
            # Look for year after month name
            year_match = re.search(rf"{month_name}\s+(\d{{4}})", query_lower)
            if year_match:
                year = int(year_match.group(1))
                return f"{year}-{month_num:02d}"
            
            # Look for year before month name (e.g., "2025 january")
            year_match = re.search(rf"(\d{{4}})\s+{month_name}", query_lower)
            if year_match:
                year = int(year_match.group(1))
                return f"{year}-{month_num:02d}"
            
            # No year mentioned, assume current year
            return f"{current_date.year}-{month_num:02d}"
    
    # Check for YYYY-MM or MM/YYYY format
    date_match = re.search(r"(\d{4})-(\d{2})", query_lower)
    if date_match:
        year, month = date_match.groups()
        return f"{year}-{month}"
    
    date_match = re.search(r"(\d{2})/(\d{4})", query_lower)
    if date_match:
        month, year = date_match.groups()
        return f"{year}-{month}"
    
    # No date found, default to January 2026
    return "2026-01"


def _infer_date_parameter(agent_params: dict, user_query: str, logger=None) -> dict:
    """
    Infer and set the date parameter if not already provided or override if needed.
    Uses the extracted date from query or defaults to 2026-01.
    
    Args:
        agent_params: The parameters dict from the agent.
        user_query: The user's original query.
        logger: Logger instance.
    
    Returns:
        Updated agent_params with date set.
    """
    # Extract date from user query (not from system context or agent extraction)
    inferred_date = _extract_date_from_query(user_query)
    
    # Override the date parameter with our inferred date
    agent_params["date"] = inferred_date
    
    if logger:
        logger.info(f"Date parameter set to '{inferred_date}' from query: {user_query}")
    
    return agent_params


def _extract_numeric_filter_from_query(user_query: str) -> dict:
    """
    Extract numeric filter values directly from the user's query using regex.
    This bypasses the LLM's tendency to scale numbers.
    
    Handles:
    - Plain numbers: "300", "3000000"
    - Indian units: "3 lakhs", "5 crore", "2.5L", "50k"
    - Comma-separated: "3,00,000"
    
    PRIORITY: Operator keywords (>, <, >=, <=) take precedence over plain numbers.
    
    Returns a dict with detected filter info:
    {
        "operator": ">", "<", ">=", "<=", or "" (exact match),
        "number": "300000" (the converted numeric string)
    }
    or None if no numeric filter pattern found.
    """
    query_lower = user_query.lower()
    unit_pattern = r'(?:\s*)(lakhs?|lacs?|crores?|cr|thousands?|k|l|m|million)(?:\b|$)'

    # HIGHEST PRIORITY: Patterns with OPERATOR KEYWORDS
    operator_keywords = [
        (r'(?:greater\s+than|more\s+than|above|over|exceeding)', '>'),
        (r'(?:less\s+than|lesser\s+than|below|under)', '<'),
        (r'(?:at\s+least|minimum|min)', '>='),
        (r'(?:at\s+most|maximum|max|up\s+to)', '<='),
    ]
    
    for keyword_pattern, operator in operator_keywords:
        pattern_with_unit = keyword_pattern + r'\s+([\d,]+\.?\d*)' + unit_pattern
        pattern_without_unit = keyword_pattern + r'\s+([\d,]+\.?\d*)\b'
        
        # Try with unit first
        match = re.search(pattern_with_unit, query_lower)
        if match:
            number = match.group(1).replace(",", "")
            unit = match.group(2) if match.lastindex >= 2 else ""
            if unit:
                number = _convert_indian_units(number, unit)
            return {"operator": operator, "number": number}
        
        # Try without unit
        match = re.search(pattern_without_unit, query_lower)
        if match:
            number = match.group(1).replace(",", "")
            return {"operator": operator, "number": number}

    # SECOND PRIORITY: Filter keywords ("payout 5000", "loan 3 lakhs")
    filter_patterns = [
        (r'(?:loan\s+amount|loan\s+value|loan)\s+([\d,]+\.?\d*)', ''),
        (r'(?:payout|earning|commission)\s+([\d,]+\.?\d*)', ''),
        (r'(?:amount)\s+([\d,]+\.?\d*)', ''),
    ]
    
    for pattern, operator in filter_patterns:
        pattern_with_unit = pattern + unit_pattern
        pattern_only = pattern + r'\b'
        
        # Try with unit
        match = re.search(pattern_with_unit, query_lower)
        if match:
            number = match.group(1).replace(",", "")
            unit = match.group(2) if match.lastindex >= 2 else ""
            if unit:
                number = _convert_indian_units(number, unit)
            return {"operator": operator, "number": number}
        
        # Try without unit
        match = re.search(pattern_only, query_lower)
        if match:
            number = match.group(1).replace(",", "")
            return {"operator": operator, "number": number}

    # THIRD PRIORITY: Numbers with unit suffix (3L, 50k, 2.5cr)
    attached_unit_match = re.search(r'\b([\d,]+\.?\d*)\s*(lakhs?|lacs?|crores?|cr|thousands?|k|m|million)\b', query_lower)
    if attached_unit_match:
        number = attached_unit_match.group(1).replace(",", "")
        unit = attached_unit_match.group(2)
        if len(number.replace(",", "").replace(".", "")) < 10:  # Not a phone number
            number = _convert_indian_units(number, unit)
            return {"operator": "", "number": number}

    # LAST RESORT: Any standalone number (not a phone number)
    all_numbers = re.findall(r'\b(\d[\d,]*\.?\d*)\b', user_query)
    non_phone_numbers = [n.replace(",", "") for n in all_numbers if len(n.replace(",", "").replace(".", "")) < 10]

    if non_phone_numbers:
        return {"operator": "", "number": non_phone_numbers[-1]}

    return None


def _correct_numeric_filters(filters: dict, user_query: str) -> dict:
    """
    Correct numeric filter values by extracting the actual number from the user's
    original query. This prevents the LLM from scaling/converting numbers.
    
    Uses context from the user's query to determine whether a number should apply to
    filter_loan_amount or filter_payout. Only corrects the relevant filter.
    """
    query_lower = user_query.lower()
    
    # Check which context the query is in (loan vs payout)
    has_loan_context = any(word in query_lower for word in ["loan", "loan amount", "loan value"])
    has_payout_context = any(word in query_lower for word in ["payout", "earning", "commission"])
    
    # If we have filter_loan_amount and the query mentions loans, correct it
    if "filter_loan_amount" in filters and has_loan_context:
        extracted = _extract_numeric_filter_from_query(user_query)
        if extracted:
            operator = extracted["operator"]
            number = extracted["number"]
            filters["filter_loan_amount"] = f"{operator}{number}"
        else:
            # Decode HTML entities at minimum using centralized function
            filters["filter_loan_amount"] = _clean_html_entities(filters["filter_loan_amount"])
    
    # If we have filter_payout and the query mentions payout/earning, correct it
    if "filter_payout" in filters and has_payout_context:
        extracted = _extract_numeric_filter_from_query(user_query)
        if extracted:
            operator = extracted["operator"]
            number = extracted["number"]
            filters["filter_payout"] = f"{operator}{number}"
        else:
            # Decode HTML entities at minimum using centralized function
            filters["filter_payout"] = _clean_html_entities(filters["filter_payout"])
    
    # If there's a filter_loan_amount but no loan context, just decode HTML entities
    if "filter_loan_amount" in filters and not has_loan_context:
        filters["filter_loan_amount"] = _clean_html_entities(filters["filter_loan_amount"])
    
    # If there's a filter_payout but no payout context, just decode HTML entities
    if "filter_payout" in filters and not has_payout_context:
        filters["filter_payout"] = _clean_html_entities(filters["filter_payout"])

    return filters


def _get_prompt_cache_manager(logger=None):
    """
    Get or initialize the prompt cache manager (singleton pattern with lazy initialization).
    
    Args:
        logger: Optional logger instance.
        
    Returns:
        PromptCacheManager instance.
    """
    global prompt_cache_manager
    if prompt_cache_manager is None:
        try:
            prompt_cache_manager = get_prompt_cache_manager(logger=logger)
            if logger:
                logger.info("Initialized prompt cache manager")
        except Exception as e:
            if logger:
                logger.warning(f"Failed to initialize prompt cache manager: {e}. Continuing without caching.")
            # Return None to signal that caching is unavailable
            return None
    return prompt_cache_manager


def run_agent(
    user_query: str,
    vendor: str = None,
    logger = None,
    use_cache: bool = True,
) -> AgentResponse:
    """
    Run the agent to classify intent and extract parameters from the user query.
    
    Implements prompt caching for system prompts and tool definitions to reduce
    latency and API costs.

    Args:
        user_query: The natural language query from the user.
        vendor: Optional vendor ID if already known from context.
        logger: Logger instance for debugging.
        use_cache: Whether to use prompt caching (default True).

    Returns:
        AgentResponse with the determined action and extracted parameters.
    """
    # Build dynamic context (vendor + date)
    dynamic_context = ""
    if vendor:
        dynamic_context += f"The current vendor's mobile number/ID is: {vendor}\n"

    # Inject current date so relative date references resolve correctly
    today = datetime.now()
    current_date_str = today.strftime("%Y-%m-%d")
    current_month_str = today.strftime("%Y-%m")
    last_month = today.replace(day=1) - timedelta(days=1)
    last_month_str = last_month.strftime("%Y-%m")
    dynamic_context += (
        f"Today's date is: {current_date_str}\n"
        f"Current month: {current_month_str}\n"
        f"Last month: {last_month_str}\n"
        f"Current year: {today.year}"
    )

    system_content = SYSTEM_PROMPT + "\n" + dynamic_context

    # Initialize cache manager if caching is enabled
    cache_manager = None
    if use_cache:
        cache_manager = _get_prompt_cache_manager(logger=logger)
        if cache_manager:
            try:
                # Prepare cache control configuration
                cache_config = cache_manager.prepare_cached_bedrock_request(
                    system_prompt=SYSTEM_PROMPT,
                    tools=TOOLS,
                )
                if logger:
                    logger.info(f"Prompt caching enabled for Bedrock request")
            except Exception as e:
                if logger:
                    logger.warning(f"Failed to prepare cache control: {e}. Proceeding without caching.")
                cache_manager = None

    messages = [
        {"role": "user", "content": [{"text": user_query}]},
    ]

    # Build Bedrock request with optional cache control
    bedrock_request_kwargs = {
        "modelId": settings.BEDROCK_MODEL_ID,
        "system": [{"text": system_content}],
        "messages": messages,
        "toolConfig": {"tools": TOOLS},
    }
    
    # Caching is managed by cache_manager initialization
    if cache_manager and use_cache:
        if logger:
            logger.debug("Prompt caching prepared for Bedrock request")

    response = bedrock_client.converse(**bedrock_request_kwargs)
    
    if logger:
        logger.info(f"Raw Agent response : {response}")
        # Log cache usage metrics if available
        if "usage" in response:
            usage = response.get("usage", {})
            if logger:
                logger.info(f"Bedrock usage - Input tokens: {usage.get('inputTokens', 0)}, "
                           f"Output tokens: {usage.get('outputTokens', 0)}")
    
    output = response["output"]["message"]
    stop_reason = response["stopReason"]

    # If the model wants to use a tool
    if stop_reason == "tool_use":
        for block in output["content"]:
            if "toolUse" in block:
                tool_use = block["toolUse"]
                params = tool_use["input"]

                # Separate filter params from API params
                filters = {}
                api_params = {}
                for key, value in params.items():
                    if key.startswith("filter_") and value:
                        filters[key] = value
                    else:
                        api_params[key] = value

                # Infer date if not provided
                if tool_use["name"] == "check_payout_status":
                    api_params = _infer_date_parameter(api_params, user_query, logger)

                # Correct numeric filter values by extracting from original user query
                filters = _correct_numeric_filters(filters, user_query)

                return AgentResponse(
                    action=tool_use["name"],
                    parameters=api_params,
                    message=None,
                    filters=filters,
                )

    # If the model responds with text (needs clarification or general response)
    text_parts = []
    for block in output["content"]:
        if "text" in block:
            text_parts.append(block["text"])

    return AgentResponse(
        action=None,
        parameters={},
        message="\n".join(text_parts) if text_parts else "I couldn't understand your request.",
    )


def _parse_numeric(value) -> float:
    """Convert a value to float. Handles strings with commas/symbols and numeric types."""
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace(",", "").replace(" ", "").replace("₹", "").replace("Rs", "").replace("rs", "").strip()
    return float(cleaned)


def _matches_numeric_filter(value: str, filter_expr: str) -> bool:
    """
    Check if a numeric value matches a filter expression.
    Supports: ">300", "<5000", ">=1000", "<=500", "1000-5000", "5000" (exact).
    """
    try:
        numeric_value = _parse_numeric(value)
    except (ValueError, TypeError):
        return False

    filter_expr = filter_expr.strip()

    # Decode HTML entities using centralized function
    filter_expr = _clean_html_entities(filter_expr)

    # Range: "1000-5000"
    if "-" in filter_expr and not filter_expr.startswith("-") and not filter_expr.startswith(">") and not filter_expr.startswith("<"):
        parts = filter_expr.split("-", 1)
        try:
            low = float(parts[0].strip())
            high = float(parts[1].strip())
            return low <= numeric_value <= high
        except (ValueError, IndexError):
            return False

    # >=
    if filter_expr.startswith(">="):
        threshold = float(filter_expr[2:].strip())
        return numeric_value >= threshold

    # <=
    if filter_expr.startswith("<="):
        threshold = float(filter_expr[2:].strip())
        return numeric_value <= threshold

    # >
    if filter_expr.startswith(">"):
        threshold = float(filter_expr[1:].strip())
        return numeric_value > threshold

    # <
    if filter_expr.startswith("<"):
        threshold = float(filter_expr[1:].strip())
        return numeric_value < threshold

    # Exact match
    try:
        threshold = float(filter_expr)
        return numeric_value == threshold
    except ValueError:
        return False


def _fuzzy_name_match(filter_name: str, record_name: str, threshold: float = 0.90) -> bool:
    """
    Check if filter_name matches record_name using substring OR fuzzy matching.

    Returns True if:
    1. filter_name is a substring of record_name (existing behavior), OR
    2. Any word in record_name fuzzy-matches filter_name with >= threshold similarity, OR
    3. filter_name fuzzy-matches the full record_name with >= threshold similarity, OR
    4. Any word in filter_name fuzzy-matches any word in record_name with >= threshold.

    Uses difflib.SequenceMatcher (no external dependencies).
    """
    filter_lower = filter_name.lower().strip()
    record_lower = record_name.lower().strip()

    if not filter_lower or not record_lower:
        return False

    # 1. Substring match (fast path)
    if filter_lower in record_lower:
        return True

    # 2. Full string fuzzy match
    if SequenceMatcher(None, filter_lower, record_lower).ratio() >= threshold:
        return True

    # 3. Filter name vs each word in record name
    record_words = record_lower.split()
    for word in record_words:
        if SequenceMatcher(None, filter_lower, word).ratio() >= threshold:
            return True

    # 4. Each word in filter name vs each word in record name
    filter_words = filter_lower.split()
    if len(filter_words) > 1:
        for fw in filter_words:
            for rw in record_words:
                if SequenceMatcher(None, fw, rw).ratio() >= threshold:
                    return True

    return False


def _apply_filters_to_agreements(agreements: list, filters: dict) -> list:
    """
    Apply filter criteria to a list of agreement records deterministically.
    Returns only the agreements matching ALL filters.
    """
    filtered = []
    for agreement in agreements:
        match = True

        if "filter_loan_amount" in filters:
            loan_amount = agreement.get("loan_amount", "0")
            if not _matches_numeric_filter(loan_amount, filters["filter_loan_amount"]):
                match = False

        if "filter_payout" in filters:
            payout = agreement.get("payout", "0")
            if not _matches_numeric_filter(payout, filters["filter_payout"]):
                match = False

        if "filter_status" in filters:
            status = agreement.get("status", "").lower()
            filter_status = filters["filter_status"].lower()
            if filter_status not in status:
                match = False

        if "filter_name" in filters:
            customer_name = agreement.get("customer_name", "").lower()
            filter_name = filters["filter_name"].lower()
            if not _fuzzy_name_match(filter_name, customer_name):
                match = False

        if match:
            filtered.append(agreement)

    return filtered


def _clean_html_entities(text: str) -> str:
    """
    Decode HTML entities in text using standard library.
    Handles: &lt;, &gt;, &le;, &ge;, &amp;, &quot;, &apos;, and more.
    """
    import html
    return html.unescape(text)


def filter_and_summarize(
    user_query: str,
    api_response: dict,
    filters: dict,
    logger=None,
    use_cache: bool = True,
) -> dict:
    """
    Filter the raw API response deterministically based on extracted filter criteria.
    Uses Python code for numeric/string comparisons instead of relying on LLM.

    Args:
        user_query: The original natural language query from the user.
        api_response: The raw JSON response from the payout API.
        filters: Dictionary of filter criteria extracted by the agent.
        logger: Optional logger instance.
        use_cache: Deprecated parameter (ignored). Kept for backward compatibility.

    Returns:
        A dict with 'filtered_data' (same format as API) and 'reasoning' (explanation).
    """
    # Guard: if API returned an error, pass it through without filtering
    if not api_response:
        return {
            "filtered_data": None,
            "reasoning": "Unable to fetch payout data: No response from API.",
        }

    # Check for actual errors (exclude "no_agreements_found" which is not a real error)
    if api_response.get("result") == "error":
        error_msg = api_response.get("error_message", api_response.get("message", "Unknown API error"))
        # If it's specifically "no agreements found", treat as no data (not an error)
        if error_msg == "no_agreements_found":
            return {
                "filtered_data": None,
                "reasoning": "No agreements found",
            }
        return {
            "filtered_data": None,
            "reasoning": f"Unable to fetch payout data: {error_msg}",
        }

    # Apply deterministic filtering on agreements list
    agreements = api_response.get("agreements", [])
    total_records = len(agreements)

    # Fallback: if no filter_name was extracted by LLM, try to detect name from query
    if "filter_name" not in filters and user_query and agreements:
        name_fields = ["customer_name", "borrower_name", "name"]
        detected_name = _detect_name_from_query(user_query, agreements, name_fields)
        if detected_name:
            filters = dict(filters)  # don't mutate original
            filters["filter_name"] = detected_name
            if logger:
                logger.info(f"Fallback name detection (payout): extracted '{detected_name}' from query '{user_query}'")

    # If no filters (even after fallback), return data as-is
    if not filters:
        if total_records == 0:
            return {
                "filtered_data": None,
                "reasoning": "No agreements found",
            }
        return {
            "filtered_data": api_response,
            "reasoning": "No filters applied. Returning all data.",
        }

    filtered_agreements = _apply_filters_to_agreements(agreements, filters)

    # If name filter was applied and no results found, return a friendly message
    if "filter_name" in filters and len(filtered_agreements) == 0:
        filter_name = filters["filter_name"]
        if logger:
            logger.info(f"Name filter '{filter_name}' matched 0 records out of {total_records}.")
        return {
            "filtered_data": None,
            "reasoning": "We couldn't find data for the given request. Please rephrase your query and try again.",
        }

    # If any filter produced empty results, return friendly message
    if len(filtered_agreements) == 0:
        if logger:
            logger.info(f"Filters {filters} matched 0 records out of {total_records}.")
        return {
            "filtered_data": None,
            "reasoning": "No data found matching your criteria. Please try a different search.",
        }

    # Build filtered response preserving the same structure
    filtered_response = dict(api_response)
    filtered_response["agreements"] = filtered_agreements

    # Build reasoning string
    filter_descriptions = []
    for key, value in filters.items():
        clean_key = key.replace("filter_", "").replace("_", " ")
        filter_descriptions.append(f"{clean_key}: {value}")

    reasoning = _clean_html_entities(
        f"Applied filters: {', '.join(filter_descriptions)}. "
        f"Total records in input: {total_records}. "
        f"Matching records found: {len(filtered_agreements)}."
    )

    if logger:
        logger.info(f"Deterministic filter result — {reasoning}")

    return {
        "filtered_data": filtered_response,
        "reasoning": reasoning,
    }


def _detect_name_from_query(user_query: str, records: list, name_fields: list) -> str | None:
    """
    Fallback name detection: scan words in the user's query and check if any word
    partially matches a customer name in the API response records.

    This handles cases where the LLM fails to extract filter_name but the user
    clearly mentioned a customer name (e.g., "show me bablu lead" where "bablu sarkar"
    exists in the response).

    Args:
        user_query: The original user query.
        records: List of record dicts from the API response.
        name_fields: List of field names to check for customer names in records.

    Returns:
        The matching query word/phrase if found, or None.
    """
    if not user_query or not records:
        return None

    # Common stop words that should NOT be treated as names
    stop_words = {
        "show", "me", "my", "the", "a", "an", "is", "are", "was", "were",
        "lead", "leads", "payout", "payouts", "status", "details", "detail",
        "of", "for", "in", "on", "at", "to", "from", "with", "by",
        "all", "only", "pending", "paid", "failed", "sanctioned", "rejected",
        "disbursed", "submitted", "under", "review", "loan", "amount",
        "greater", "less", "than", "above", "below", "more", "customer",
        "borrower", "name", "mobile", "number", "ka", "ki", "ke", "hai",
        "kya", "dikhao", "dikha", "do", "batao", "bata", "check", "get",
        "fetch", "find", "search", "filter", "list", "what", "how", "when",
        "where", "which", "who", "this", "that", "these", "those",
        "last", "month", "year", "january", "february", "march", "april",
        "may", "june", "july", "august", "september", "october", "november",
        "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep",
        "oct", "nov", "dec", "today", "yesterday", "tomorrow",
    }

    query_lower = user_query.lower().strip()
    # Split query into individual words
    query_words = [w for w in re.split(r'\s+', query_lower) if w and w not in stop_words and not w.isdigit() and len(w) > 2]

    if not query_words:
        return None

    # Collect all customer names from the records
    customer_names = []
    for record in records:
        for field in name_fields:
            name_val = record.get(field, "")
            if name_val:
                customer_names.append(str(name_val).lower())
        # Also build full name from first_name + last_name
        first = record.get("first_name", "")
        last = record.get("last_name", "")
        if first and last:
            customer_names.append(f"{first} {last}".lower())

    if not customer_names:
        return None

    # Check if any query word is a substring or fuzzy match of any customer name
    for word in query_words:
        for name in customer_names:
            if word in name:
                return word
            # Fuzzy match: check word against each word in the customer name
            name_words = name.split()
            for nw in name_words:
                if len(word) >= 3 and len(nw) >= 3 and SequenceMatcher(None, word, nw).ratio() >= 0.90:
                    return word

    # Also check 2-word combinations (bigrams) from the query for full name matches
    query_word_list = re.split(r'\s+', query_lower)
    non_stop_indices = [i for i, w in enumerate(query_word_list) if w not in stop_words and not w.isdigit() and len(w) > 2]
    for i in range(len(non_stop_indices) - 1):
        idx1, idx2 = non_stop_indices[i], non_stop_indices[i + 1]
        if idx2 - idx1 <= 2:  # words are close together
            bigram = f"{query_word_list[idx1]} {query_word_list[idx2]}"
            for name in customer_names:
                if bigram in name:
                    return bigram
                # Fuzzy match bigram against full name
                if SequenceMatcher(None, bigram, name).ratio() >= 0.90:
                    return bigram

    return None


def filter_leads(api_response: dict, filters: dict, user_query: str = None, logger=None) -> dict:
    """
    Filter the lead status API response deterministically based on extracted filter criteria.
    Includes fallback name detection when LLM doesn't extract filter_name.

    Args:
        api_response: The raw JSON response from the lead status API.
        filters: Dictionary of filter criteria extracted by the agent.
        user_query: The original user query (used for fallback name detection).
        logger: Logger instance.

    Returns:
        A dict with 'filtered_data' and 'reasoning'.
    """
    # Allowed keywords for filter_status in check_lead_status
    ALLOWED_LEAD_STATUS_KEYWORDS = {"login", "in progress", "disbursed", "rejected", "lead closed"}
    
    # Mapping from user input keywords to actual show_status values
    STATUS_KEYWORD_MAPPING = {
        "login": ["Login"],
        "in progress": ["Docs Collections In Process", "In Progress", "Interested", "Unable To Connect", "Follow-up Required"],
        "disbursed": ["In Disbursal Stage"],
        "rejected": ["Rejected", "Cancelled"],
        "lead closed": ["Not Interested", "Not Eligible", "Interested In Other Product"],
    }
    
    # Validate filter_status if present - only allow specified keywords
    if "filter_status" in filters:
        filter_status_value = filters["filter_status"].lower().strip()
        if filter_status_value not in ALLOWED_LEAD_STATUS_KEYWORDS:
            if logger:
                logger.info(f"Invalid filter_status value '{filters['filter_status']}'. Allowed values: {ALLOWED_LEAD_STATUS_KEYWORDS}. Removing filter_status.")
            # Remove invalid filter_status
            filters = dict(filters)  # don't mutate original
            del filters["filter_status"]
        else:
            # Map user keyword to actual show_status values
            filters = dict(filters)  # don't mutate original
            user_keyword = filter_status_value
            mapped_statuses = STATUS_KEYWORD_MAPPING.get(user_keyword, [])
            filters["_mapped_statuses"] = mapped_statuses
            if logger:
                logger.info(f"Mapped user keyword '{user_keyword}' to show_status values: {mapped_statuses}")
    
    # Guard: if API returned an error, pass it through without filtering
    if not api_response:
        return {
            "filtered_data": None,
            "reasoning": "Unable to fetch lead data: No response from API.",
        }
    
    # Check for error in top-level result (string "error" vs dict with leads)
    if api_response.get("result") == "error":
        error_msg = api_response.get("message", "Unknown API error")
        # Avoid duplicating the error prefix if it's already in the message
        if error_msg.startswith("Currently, unable to fetch the data"):
            reasoning = error_msg
        else:
            reasoning = f"Unable to fetch lead data: {error_msg}"
        return {
            "filtered_data": None,
            "reasoning": reasoning,
        }

    # The lead API response has leads nested inside 'result.leads'
    # Also check top-level 'leads' or 'data' as fallback
    if "result" in api_response and isinstance(api_response["result"], dict):
        leads = api_response["result"].get("leads", [])
    else:
        leads = api_response.get("leads", api_response.get("data", []))
    if not isinstance(leads, list):
        leads = []

    # Fallback: if no filter_name was extracted by LLM, try to detect name from query
    if "filter_name" not in filters and user_query and leads:
        name_fields = ["customer_name", "name", "applicant_name", "first_name"]
        detected_name = _detect_name_from_query(user_query, leads, name_fields)
        if detected_name:
            filters = dict(filters)  # don't mutate original
            filters["filter_name"] = detected_name
            if logger:
                logger.info(f"Fallback name detection: extracted '{detected_name}' from query '{user_query}'")

    # If no filters, return data as-is or "no data" if empty
    if not filters:
        if len(leads) == 0:
            return {
                "filtered_data": None,
                "reasoning": "No leads available",
            }
        return {
            "filtered_data": api_response,
            "reasoning": "No filters applied. Returning all leads.",
        }

    total_records = len(leads)
    filtered_leads = []
    for lead in leads:
        match = True

        # Filter by name (partial, case-insensitive + fuzzy match at 90%)
        if "filter_name" in filters:
            lead_name = lead.get("customer_name", lead.get("name", lead.get("applicant_name", lead.get("first_name", "")))).lower()
            last_name = lead.get("last_name", "")
            if last_name:
                lead_name = f"{lead_name} {last_name}".lower()
            filter_name = filters["filter_name"].lower()
            if not _fuzzy_name_match(filter_name, lead_name):
                match = False

        # Filter by mobile number
        if "filter_mobile" in filters:
            lead_mobile = str(lead.get("customer_mobile", lead.get("mobile", lead.get("mobile_number", ""))))
            filter_mobile = filters["filter_mobile"].strip()
            if filter_mobile not in lead_mobile:
                match = False

        # Filter by loan amount
        if "filter_loan_amount" in filters:
            loan_amount = lead.get("loan_amount", lead.get("amount", "0"))
            if not _matches_numeric_filter(loan_amount, filters["filter_loan_amount"]):
                match = False

        # Filter by status (using mapped show_status values)
        if "_mapped_statuses" in filters:
            lead_status = lead.get("show_status", "").strip()
            mapped_statuses = filters["_mapped_statuses"]
            # Check if lead's show_status matches any of the mapped values (case-insensitive)
            if not any(lead_status.lower() == status.lower() for status in mapped_statuses):
                match = False

        if match:
            filtered_leads.append(lead)

    # If name filter was applied and no results found, return friendly message
    if "filter_name" in filters and len(filtered_leads) == 0:
        if logger:
            logger.info(f"Lead name filter '{filters['filter_name']}' matched 0 records out of {total_records}.")
        return {
            "filtered_data": None,
            "reasoning": "No leads found with that name. Please check the spelling and try again.",
        }

    # If any filter produced empty results, return friendly message
    if len(filtered_leads) == 0:
        if logger:
            logger.info(f"Lead filters {filters} matched 0 records out of {total_records}.")
        return {
            "filtered_data": None,
            "reasoning": "No leads found matching your criteria. Please try a different search.",
        }

    # Build filtered response preserving structure
    filtered_response = dict(api_response)
    if "result" in api_response and isinstance(api_response["result"], dict):
        filtered_response["result"] = dict(api_response["result"])
        filtered_response["result"]["leads"] = filtered_leads
    elif "leads" in api_response:
        filtered_response["leads"] = filtered_leads
    elif "data" in api_response:
        filtered_response["data"] = filtered_leads
    else:
        filtered_response["leads"] = filtered_leads

    # Build reasoning string
    filter_descriptions = []
    for key, value in filters.items():
        # Skip internal mapped_statuses key from descriptions
        if key == "_mapped_statuses":
            continue
        clean_key = key.replace("filter_", "").replace("_", " ")
        filter_descriptions.append(f"{clean_key}: {value}")
    
    # Add mapped statuses to description if present
    if "_mapped_statuses" in filters:
        mapped_statuses = filters["_mapped_statuses"]
        filter_descriptions.insert(0, f"status: {', '.join(mapped_statuses)}")

    reasoning = _clean_html_entities(
        f"Applied filters: {', '.join(filter_descriptions)}. "
        f"Total records in input: {total_records}. "
        f"Matching records found: {len(filtered_leads)}."
    )

    if logger:
        logger.info(f"Lead filter result — {reasoning}")

    return {
        "filtered_data": filtered_response,
        "reasoning": reasoning,
    }


def find_faq_answer(question: str, logger=None) -> dict:
    """
    Find the best matching FAQ answer for a user's question using keyword/semantic matching.
    Uses the LLM to pick the best match from the knowledge base.

    Args:
        question: The user's question as extracted by the agent.
        logger: Logger instance.

    Returns:
        A dict with 'answer' field containing the FAQ response.
    """
    from app.services.connector_faq_kb import FAQ_KNOWLEDGE_BASE

    # Build a numbered list of questions for the LLM to pick from
    question_list = ""
    for i, faq in enumerate(FAQ_KNOWLEDGE_BASE):
        question_list += f"{i + 1}. {faq['question']}\n"

    faq_match_prompt = f"""You are a FAQ matching assistant. Given a user's question, find the BEST matching question from the list below and return its number.

User's question: "{question}"

Available FAQ questions:
{question_list}

Rules:
- Return ONLY a JSON object in this format: {{"match_index": <number>, "confidence": "high"|"medium"|"low"}}
- If the user's question closely matches one of the FAQs (same topic, same intent), return that number with "high" confidence.
- If it partially matches (related topic but different angle), return the closest match with "medium" confidence.
- If no FAQ is even remotely relevant, return {{"match_index": 0, "confidence": "none"}}
- ONLY output the JSON object. No extra text.
"""

    messages = [
        {"role": "user", "content": [{"text": faq_match_prompt}]},
    ]

    try:
        response = bedrock_client.converse(
            modelId=settings.BEDROCK_MODEL_ID,
            system=[{"text": "You are a precise FAQ matching assistant. Return only valid JSON."}],
            messages=messages,
        )

        if logger:
            logger.info(f"FAQ match agent response: {response}")

        output = response["output"]["message"]
        text_parts = []
        for block in output["content"]:
            if "text" in block:
                text_parts.append(block["text"])

        raw_text = "".join(text_parts).strip()
        result = json.loads(raw_text)

        match_index = result.get("match_index", 0)
        confidence = result.get("confidence", "none")

        if match_index > 0 and confidence in ("high", "medium"):
            faq_entry = FAQ_KNOWLEDGE_BASE[match_index - 1]
            return {
                "answer": faq_entry["answer"],
                "matched_question": faq_entry["question"],
                "category": faq_entry["category"],
                "confidence": confidence,
            }
        else:
            return {
                "answer": "I'm sorry, I don't have information about that. You can call our helpdesk at 1800-123-4567 or contact your RM for assistance.",
                "matched_question": None,
                "category": None,
                "confidence": "none",
            }

    except Exception as e:
        if logger:
            logger.exception(f"Exception in FAQ matching: {e}")
        return {
            "answer": "I'm sorry, I couldn't process your question right now. Please try again or call our helpdesk at 1800-123-4567.",
            "matched_question": None,
            "category": None,
            "confidence": "none",
        }
