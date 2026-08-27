from pydantic import BaseModel, field_validator
from typing import Optional, Union

class AgentRequest(BaseModel):
    query_input: str
    session_id: str
    mobile_no: str
    user_text_flag: Optional[int] = 0
    show_more_req_flag: Optional[str] = "0"
    query_no: Optional[str] = "0"
    lead_capture: Optional[str] = "0"
    verification_code: Optional[str] = ""
    otp_verified: Optional[str] = "0"
    user_request: Optional[str] = ""
    show_all_loans: str = "0"
    selected_lang: str = "en"
    
class HRAgentRequest(BaseModel):
    user_question: str
    session_id: str
    employee_id: str
    mobile_number: str
    zone: str

# Agent response: the inner "message" object
class AgentMessage(BaseModel):
    response: Union[str, dict, list, None] = None
    type: Optional[str] = "string"
    retry_flag: Optional[int] = 0
    loan_api_failure_flag: Optional[int] = 0
    counter_flag_agg: Optional[int] = 0

    # greeting flow
    intent_dict: Optional[dict[str, str]] = None

    # OTP flow
    otp_verified: Optional[str] = None
    flow_type: Optional[str] = None

    # My Loans flow
    sr_flag: Optional[int] = None
    sr_text: Optional[str] = None
    loan_count: Optional[int] = None
    apply_loan_flag: Optional[int] = None

    # Apply Loan flow
    cust_details_flag: Optional[int] = None
    cust_api_status: Optional[int] = None
    product_type: Optional[str] = None
    product_type_flag: Optional[int] = None

    model_config = {"extra": "allow"}


# Agent response: the outer envelope
class AgentResponse(BaseModel):
    message: AgentMessage
    detected_mobile_no: str = ""
    response_code: int = 200


# HR Agent: inner response object from Bedrock
class HRAgentResult(BaseModel):
    status_code: int
    result_text: str


# HR Agent: outer envelope
class HRAgentResponse(BaseModel):
    success: bool
    response: HRAgentResult


class QueryRequest(BaseModel):
    message: str
    vendor: str  # Mandatory field. Vendor identifier
    vendor_id: Optional[str] = ""  # Vendor identifier (optional, defaults to empty string)
    vertical: Optional[str] = "LAP"  # Optional field. Valid values: LAP (Loan Against Property), HL (Home Loan), SME (Small and Medium Enterprise). Defaults to LAP.

    @field_validator('vertical', mode='before')
    @classmethod
    def validate_vertical(cls, v):
        """
        Validate that vertical is one of the allowed values.
        Uses LAP as default if not provided.
        """
        valid_verticals = ["LAP", "HL", "SME"]
        
        # Use default value if None is provided
        if v is None:
            return "LAP"
        
        v_str = str(v).upper().strip()
        
        if not v_str:
            return "LAP"
        
        if v_str not in valid_verticals:
            raise ValueError(f"Invalid vertical '{v}'. Must be one of: {', '.join(valid_verticals)}")
        
        return v_str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message": "Show me only pending payouts for January 2026",
                    "vendor": "9876543210",
                    "vertical": "LAP",
                },
                {
                    "message": "What is the payout status for customer Ravi in Jan 2026?",
                    "vendor": "9876543210",
                    "vertical": "HL",
                },
                {
                    "message": "Show loans above 50000 that are still pending",
                    "vendor": "9876543210",
                    "vertical": "SME",
                },
                {
                    "message": "I haven't received my payment for last month, please help",
                    "vendor": "9876543210",
                    "vertical": "LAP",
                },
            ]
        }
    }


class QueryResponse(BaseModel):
    intent: Optional[str] = None
    message: Optional[str] = None
    answer: Optional[str] = None
    reasoning: Optional[str] = None
    filters_applied: Optional[dict] = None
    filtered_response: Optional[dict] = None
    raw_api_response: Optional[dict] = None


# Image Extract Request Parameter
class ImageExtractRequest(BaseModel):
    base64_pdf: str

# Image Extract Request Parameter
class ImageExtractResponse(BaseModel):
    base64_img: str
    file_format: str

class NameMatchRequest(BaseModel):
    pan_name: str
    aadhar_name: str
    threshold: float = 0.7

class NameMatchResponse(BaseModel):
    matched_flag: bool
    similarity_score: int
    pan_name_normalized: str
    aadhar_name_normalized: str

class ImageMergeRequest(BaseModel):
    first_image: str
    second_image: Optional[str] = None

class ImageMergeResponse(BaseModel):
    merged_image: str  # S3 presigned URL for merged/converted image

