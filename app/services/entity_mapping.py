"""
Entity mapping service.

Handles:
- Intent to API routing
- Loan detail retrieval
- Service request document APIs
- Redis pagination flow
- Mock-mode responses for local development
"""


import json
import os   
from app.core.logging import *
from app.core.http_client import async_client
from app.utils.redis_cache import *
from app.core.config import settings
from app.core.constants import *
from app.utils.text_utils import process_input


async def get_loan_details(url, mobile_no, addl_mobile_number, loan_spec_flag, entity_received, logger):
    """
    Fetch loan portfolio details from CholaOne APIs.

    Supports:
    - All-loan retrieval
    - Product-specific loan filtering
    - Loan response normalization
    """

    response = {}
    res = {}
    result = {}
    combined_data = []

    resp_count = 0
    loan_api_failure_flag = 0

    try:
        headers = {
              'Content-Type': 'application/json'
            }

        payload = json.dumps({
            "mobile_number" : mobile_no,
            "addl_mobile_number" : addl_mobile_number
        })

        logger.info(f"received request for {entity_received} loan details")
        logger.info(f"url: {url}")
        logger.info(f"payload: {payload}")

        # CholaOne API call for fetching loan portfolio
        # Async API call to downstream loan service
        resp = await async_client.post(url, headers=headers, content=payload)

        status_code = resp.status_code
        resp = json.loads(resp.text)

        logger.info(f"response from loan_details api : {resp}")

        # Maps short loan product codes to readable labels
        product_type_abbrev = LOAN_PRODUCT_TYPE_ABBREV

        if "data" in resp.keys():

            item_count = len(resp["data"].items())

            for product_type, loans in resp["data"].items():

                # Returns all loans if specific loan type was not requested
                if(loan_spec_flag == 0):

                    result[product_type] = [
                        {
                            "agreement_number": loan["loanAgreementNumber"],
                            "emi_amount": loan["emi"],
                            "loanStatus": loan["loanStatus"],
                            "vehicle_number": loan["vehicleNumber"],
                            "short_type": loan["productType"],
                            "product_type": product_type_abbrev[loan["productType"].lower()]
                        }
                        for loan in loans
                    ]

                # Filter only the requested loan category
                else:

                    result[product_type] = [
                        {
                            "agreement_number": loan["loanAgreementNumber"],
                            "emi_amount": loan["emi"],
                            "loanStatus": loan["loanStatus"],
                            "vehicle_number": loan["vehicleNumber"],
                            "short_type": loan["productType"],
                            "product_type": product_type_abbrev[loan["productType"].lower()]
                        }
                        for loan in loans
                        if loan["productType"].lower() == entity_received.replace("_",'')
                    ]

            logger.info(f"response from loan_details function before counter: {result}")

            # Turning grouped product response into a single list
            for i in result.keys():
                combined_data += result[i]

            logger.info(f'combined_data : {combined_data}')

            res['data'] = combined_data

            count_ = 0

            # Counts total number of loans returned
            for k, v in result.items():
                c = 0
                p = result[k]
                x = c + len(p)
                count_ = x + count_

            response = res['data']
            resp_count = count_

            logger.info(f"final response from the loan details function : {response} and response count {resp_count}")

            return response, resp_count, loan_api_failure_flag

        else:

            # Distinguish backend failure vs no-loan cases
            if(status_code == 500 and resp['code'] in [500, 1013,40009]):
                loan_api_failure_flag = 2
                response = str(resp['message'])

            else:
                loan_api_failure_flag = 1

            logger.info(f'@@response : {response}')
            return response, resp_count, loan_api_failure_flag

    except Exception as e:
        logger.exception(f'Exception in loan_details function {e}')
        return response, resp_count, loan_api_failure_flag


async def service_request(url, mobile_no, addl_mobile_number, agreement_no, logger):
    try:
        headers = {
            'Content-Type': 'application/json'
            }
        payload = json.dumps({
                  "mobile_number": mobile_no,
                  "agreement_number": agreement_no,
                  "addl_mobile_number": addl_mobile_number
                })

        logger.info(f"payload sent to the service request : {payload}")

        # Generic SR API wrapper for downloadable documents.
        response = await async_client.post(url, headers=headers, content=payload)
        response = response.text
        logger.info(f"response from service_request function : {response}")
        return response

    except Exception as e:
        logger.exception(e)
        return None


async def payment_history_schedule(url, mobile_no, addl_mobile_number, agreement_no, logger):
    try:
        headers = {
              'Content-Type': 'application/json'
            }
        payload = json.dumps({
            "mobile_number": mobile_no,
            "agreement_number": agreement_no,
            "addl_mobile_number": addl_mobile_number,
            "request_type": "download"
            })

        # Download-based APIs require request_type explicitly.
        response = await async_client.post(url, headers=headers, content=payload)
        response = response.text
        logger.info(f"response from payment_history function : {response}")
        return response

    except Exception as e:
        logger.exception(e)
        return None


async def entity_mapping(entity, query_input, mobile_no, addl_mobile_number,
                   agreement_no, session_id, logger,
                   redis_client, redis_key_name,  show_all_loans=0):
    try:

        # Mock mode bypasses downstream integrations for local testing/demo.
        if str(os.getenv("MOCK_MODE", "false")).strip().lower() in ("1", "true", "yes", "on"):

            mock_loan_list = [
                {
                    "agreement_number": "VFMOCK0000001",
                    "emi_amount": "5000",
                    "loanStatus": "Active",
                    "vehicle_number": "TN01AB1234",
                    "short_type": "VF",
                    "product_type": "Vehicle Loans"
                },
                {
                    "agreement_number": "HLMOCK0000002",
                    "emi_amount": "15000",
                    "loanStatus": "Active",
                    "vehicle_number": "",
                    "short_type": "HL",
                    "product_type": "Home Loans"
                }
            ]

            final_dict = {
                "response": mock_loan_list,
                "sr_entity": entity
            }

            return final_dict, len(mock_loan_list), 0, 0

        logger.info(f'entity recived in by entity_mapping function {entity}')

        final_dict = {}

        # Master entity list supported by orchestration flow.
        entities_ = ENTITY_MAPPING_ENTITIES

        final_dict['sr_entity'] = ""

        # Normalize entity to exact supported keyword.
        for i in entities_:
            if i in entity:
                entity = i
                break

        entity = process_input(entity, logger)

        entity_received = entity
        entity_to_pass = entity

        loan_spec_flag = 0
        resp_count = 0
        rem_flag = 0
        loan_api_failure_flag = 0
        sr_entitycheck_flag = 0

        logger.info(f'entity processed in entity_mapping function {entity_received}')

        # Product-specific intents internally map to loan_details API.
        if(entity_received in ["csel_", "vf_", "hl_", "lap_", "sbpl_", "sme_", "gl_"]):

            loan_spec_flag = 1
            entity_received = "loan_details_"

        if(entity_received):

            # Entity-to-endpoint routing table.
            api_dict = {k: settings.CHOLAONE_DOMAIN + v for k, v in ENTITY_MAPPING_API_PATHS.items()}

            if entity_received in ENTITY_MAPPING_URL_KEYS:

                url = api_dict[entity_received]
                sr_entitycheck_flag = 1

        logger.info(f'@@Entity received@@ : {entity}')

        if(entity_received == "loan_details_" or loan_spec_flag == 1):

            # Loan APIs can return large responses; Redis helps paginate them.
            cholaone_response, cholaone_resp_count, loan_api_failure_flag = await get_loan_details(
                url,
                mobile_no,
                addl_mobile_number,
                loan_spec_flag,
                entity_to_pass,
                logger
            )

            if(redis_client != None and cholaone_resp_count):

                logger.info("Inside entity mapping redis injestion.......\n")

                response, resp_count, rem_flag = create_ans_dict(
                    redis_client,
                    redis_key_name,
                    cholaone_response,
                    logger
                )

                logger.info(f'response : {response} \n resp_count : {resp_count} \n rem_flag : {rem_flag}')

            elif(redis_client == None and cholaone_resp_count):

                logger.info("Redis is not available.......\n")

                if(cholaone_resp_count > 0):

                    response = cholaone_response
                    resp_count = cholaone_resp_count
                    rem_flag = 0

                    logger.info(f'response : {response} \n resp_count : {resp_count} \n rem_flag : {rem_flag}')

            elif(cholaone_resp_count == 0):

                response = cholaone_response
                resp_count = cholaone_resp_count
                rem_flag = 0

                logger.info(f'response : {response} \n resp_count : {resp_count} \n rem_flag : {rem_flag}')

        else:

            # Service-document APIs.
            if(entity == "welcome_letter_" or
               entity == "mini_soa_" or
               entity == "loan_summary_"):

                response = await service_request(
                    url,
                    mobile_no,
                    addl_mobile_number,
                    agreement_no,
                    logger
                )

            # Download-oriented APIs.
            elif(entity == "payment_history_" or entity == "payment_schedule_"):

                response = await payment_history_schedule(
                    url,
                    mobile_no,
                    addl_mobile_number,
                    agreement_no,
                    logger
                )

            # Default fallback response.
            else:
                response = entity

        # Normalize string responses if required.
        if(isinstance(response, str)):

            if(resp_count):

                response = json.loads(response)

                if 'data' in response.keys():
                    response = response['data']

                else:
                    response = response['message']

        # Unified response contract consumed by app.py.
        final_dict['response'] = response

        if(sr_entitycheck_flag):
            final_dict['sr_entity'] = entity
            
        logger.info(f'final_dict : {final_dict} \n resp_count : {resp_count} \n rem_flag : {rem_flag}')
        
        return final_dict, resp_count, rem_flag, loan_api_failure_flag

    except Exception as e:
        logger.exception(f"Exception in entity mapping..... {e}")
        return final_dict, resp_count, rem_flag, loan_api_failure_flag

