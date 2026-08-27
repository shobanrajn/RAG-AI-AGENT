# utils/text_utils.py

"""
Text / regex utility related functions.
"""
import re
import ast
import json
from app.core.constants import SR_REGEX_TEXTS, ENTITY_SUPER_LIST, APPLY_LOAN_INTENT_LIST


# Agreement number 
def get_agreement_number(query_input: str, logger) -> tuple[str, str]:
    try:
        regex_bot = r"selected agreement number\s*([A-Za-z][A-Za-z0-9]{10,})"
        regex_free_text = (
            r"\b[A-Za-z](?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{10,}\b"
        )
        regex_final = r"\b[A-Z]{2,}[A-Z0-9]*\d{4,}[A-Z0-9]*\b"

        match  = re.search(regex_bot, query_input)
        match1 = re.search(regex_free_text, query_input)
        match2 = re.search(regex_final, query_input)

        if match:
            agreement_no = match.group(1)
        elif match1:
            agreement_no = match1.group(0)
        elif match2:
            agreement_no = match2.group(0)
        else:
            agreement_no = ""

        modified_query = query_input.replace(agreement_no, "")
        logger.info(f"detected agreement_no : {agreement_no}")
        return agreement_no, modified_query
    except Exception as e:
        logger.exception(e)
        return "", query_input


# Mobile number 
def mobile_num_check(query_input: str, logger) -> tuple[str, str]:
    try:
        list_words = query_input.split()
        agg_number, modified_query = get_agreement_number(query_input, logger)
        mobile_num = ""

        if len(list_words) == 1 and query_input.isalnum():
            mobile_num = ""
        else:
            regex1 = re.search(r'(\D*(\d\D*){10})\D*$', modified_query)
            regex2 = re.search(
                r'(?<!\d)(?:\+91[-\s]?)?(?:0?91?[-\s]?)?(?:(?:\d[-\s]?){10,11})(?!\d)',
                modified_query,
            )
            if regex1:
                last_ten_digits = "".join(filter(str.isdigit, regex1.group(0)))
                if regex2:
                    mob_num = regex2.group(0)
                    logger.info(f"mobile number from regex2 : {modified_query}")
                    mobile_num = mob_num[-11:]
                logger.info(f"mobile number from regex1 : {modified_query}")
                mobile_num = last_ten_digits[-11:]
            elif regex2:
                query_input = regex2.group(0)
                logger.info(f"mobile number from regex2 : {modified_query}")
                mobile_num = modified_query[-11:]
            else:
                mobile_num = ""
        return mobile_num, agg_number
    except Exception as e:
        logger.exception(f"error in the func mobile_num_check : {e}")
        return "", agg_number


def mobile_num_validation(mobile_no: str, detected_mobile_no: str, logger) -> bool:
    try:
        regex_detected = re.findall(r"\d+", detected_mobile_no)
        logger.info(f"regex_detected_mobile_num_list : {regex_detected}")
        if regex_detected:
            extracted = regex_detected[0][len(regex_detected[0]) - 10:]
            logger.info(f"regex_detected_mobile_num : {extracted}")
            if extracted[-10:].strip() == mobile_no.strip():
                return True
            logger.info("number validation failed")
            return False
        logger.info("number validation failed")
        return False
    except Exception as e:
        logger.exception(f"error in the func mobile_num_validation : {e}")
        return False


# SR / entity text check 
def user_text_check(query_input: str, logger) -> tuple[int, str]:
    try:
        entities_ = ENTITY_SUPER_LIST
        sr_flag = 0
        sr_intent = ""

        for phrase, intent in SR_REGEX_TEXTS.items():
            if phrase in query_input.lower():
                sr_flag = 1
                sr_intent = intent
                break

        logger.info(f"sr_flag : {sr_flag} \n sr_intent : {sr_intent}")

        if sr_flag == 0:
            for i in entities_:
                if i in query_input:
                    sr_intent = i
                    sr_flag = 1
                    break
        return sr_flag, sr_intent
    except Exception as e:
        logger.exception(e)
        return 0, ""


# Intent helpers 

def extract_after_dot(text: str, phrase: str, logger) -> str:
    try:
        for line in text.splitlines():
            if phrase in line:
                dot_index = line.find(".")
                if dot_index != -1:
                    return line[dot_index + 1:].strip()
        return text
    except Exception as e:
        logger.exception(f"exception in extract_after_dot : {e}")
        return text


def convert_to_dict_if_possible(input_str, logger):
    logger.info(f"input_str in convert_to_dict_if_possible func: {input_str}")

    # ------------------------------------------------------------------
    # CF05264 - no loan available issues
    # Skip conversion for plain text responses.
    # ------------------------------------------------------------------
    if not isinstance(input_str, str):
        return input_str, "json"

    input_str = input_str.strip()

    # CF05264 - no loan available issues
    if not (input_str.startswith("{") or input_str.startswith("[")):
        return input_str, "string"

    try:
        result = ast.literal_eval(input_str)
        logger.info(f"result in convert_to_dict_if_possible func: {result}")
        return result, "json"

    except Exception as e:
        logger.exception(f"exception in convert_to_dict_if_possible : {e}")

        # ------------------------------------------------------------------
        # CF05264 - no loan available issues
        # Return original string instead of raising exception.
        # ------------------------------------------------------------------
        return input_str, "string"


def process_input(data: str, logger) -> str:
    try:
        lines = data.splitlines()
        entity = ""
        if len(lines) > 1:
            entity = lines[-1]
        else:
            entity = data
        return entity
    except Exception as e:
        logger.exception(e)
        return data


def check_agent_response(logger, intent_list: list, response: str) -> bool:
    try:
        return response not in intent_list
    except Exception as e:
        logger.info(f"Exception in checking agent response: {e}")
        return False


def find_intent(logger, response: str) -> str:
    try:
        identified_intent = response
        for intent in response.split():
            if intent in APPLY_LOAN_INTENT_LIST:
                identified_intent = intent
        return identified_intent
    except Exception as e:
        logger.info(f"Exception in find_intent: {e}")
        return response
    
def loan_verification_multiple_loan_check(input_value, logger):
    """
    Some loan API fields return either a plain string or a list of strings
    depending on whether the customer has single or multiple loan records.

    here the response normalizes and always returns a string.
    """
    try:
        if isinstance(input_value, str):
            response = input_value
        elif isinstance(input_value, list) and len(input_value) > 0:
            response = input_value[0]
        else:
            response = ''
        return response
    except Exception as e:
        logger.exception(e)
        return ''

def loan_verification(loan_against_mobilenumber_details, intent_, logger):
    try:
        resp = {}
        resp_dict = {}
        resp['cust_details_flag'] = 0
        resp['product_type_flag'] = 0
        resp['response'] = {}

        product_type,product_type_flag = product_type_identification(intent_,logger)
        if(loan_against_mobilenumber_details==None):
            loan_against_mobilenumber_details = {}
            loan_against_mobilenumber_details['status'] = 'failure'
        if(loan_against_mobilenumber_details['status'].lower()=='failure'):
            resp = {'cust_api_status' : 203,
                    'cust_details_flag' : 0,
                    'product_type' : product_type,
                    'product_type_flag' : product_type_flag,
                    'response' : 'no data available'}
        else:
            resp['cust_api_status'] = 200
            resp_dict['customer_name'] =loan_verification_multiple_loan_check(loan_against_mobilenumber_details['data']['custname'],logger)
            resp_dict['mobile_no'] = loan_verification_multiple_loan_check(loan_against_mobilenumber_details['data']['registered'],logger)
            resp_dict['pincode'] = loan_verification_multiple_loan_check(loan_against_mobilenumber_details['data']['pincode'][0],logger)
            resp['product_type'] = product_type
            resp['product_type_flag'] = product_type_flag
            resp['cust_details_flag'] = 1
            resp['response'] = resp_dict
        response = json.dumps(resp)
        logger.info(f'loan_verification_details : {response}')
        return response
    except Exception as e:
        logger.exception(e)
        return None

def product_type_identification(intent_, logger):
    try:
        product_type = ''
        product_type_flag = 0
        intent_received = intent_
        
        product_type_dict = {"vf_apply_loan":"vf",
                            "csel_apply_loan":"csel",
                            "sbpl_apply_loan":"sbpl",
                            "hl_apply_loan":"hl",
                            "gl_apply_loan":"gl",
                             "apply_loan_":""
                           }
        for i in APPLY_LOAN_INTENT_LIST:
            if i in intent_received.lower():
                product_type = product_type_dict[i.lower()]
                break
        # if(intent_received.lower() in apply_loan_intent_list):
        #     product_type = product_type_dict[intent_received.lower()]
        if(product_type != ''):
            product_type_flag = 1
        logger.info(f'apply loan response : {product_type, product_type_flag}')
        return product_type, product_type_flag
    except Exception as e:
        logger.exception(e)
        return product_type, product_type_flag