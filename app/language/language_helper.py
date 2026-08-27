from app.language.language_mapping import (
    INTENT_LANGUAGE_DICT,
    GREETING_LANGUAGE_DICT,
    ERROR_MESSAGE_LANGUAGE_DICT,
    OTP_ERROR_LANGUAGE_DICT,
    OTP_REQUEST_LANGUAGE_DICT,
    TECHNICAL_ERROR_LANGUAGE_DICT,
    FETCH_ERROR_LANGUAGE_DICT,
    MOBILE_MISMATCH_LANGUAGE_DICT,
    SPAM_MESSAGE_LANGUAGE_DICT,
    DICT_CONVERSION_MESSAGE_LANGUAGE_DICT,
    NO_LOANS_AVAILABLE_LANGUAGE_DICT
)

def get_language_mapping(lang_code="en"):

    lang_code = str(lang_code).lower()

    if lang_code not in INTENT_LANGUAGE_DICT:
        lang_code = "en"

    return {
        "intent_dict": INTENT_LANGUAGE_DICT[lang_code],
        "greeting_message": GREETING_LANGUAGE_DICT[lang_code],
        "error_message": ERROR_MESSAGE_LANGUAGE_DICT[lang_code],
        "otp_fail_message": OTP_ERROR_LANGUAGE_DICT[lang_code],
        "otp_request_message": OTP_REQUEST_LANGUAGE_DICT[lang_code],
        "technical_error_message": TECHNICAL_ERROR_LANGUAGE_DICT[lang_code],
        "fetch_error_message": FETCH_ERROR_LANGUAGE_DICT[lang_code],
        "mobile_mismatch_message": MOBILE_MISMATCH_LANGUAGE_DICT[lang_code],
        "spam_message": SPAM_MESSAGE_LANGUAGE_DICT[lang_code],
        "dict_conversion_message": DICT_CONVERSION_MESSAGE_LANGUAGE_DICT[lang_code],
        "no_loan_message": NO_LOANS_AVAILABLE_LANGUAGE_DICT[lang_code],
    }