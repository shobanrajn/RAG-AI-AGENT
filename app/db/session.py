import boto3
import redis
import ssl
import json
import aiohttp
from motor.motor_asyncio import AsyncIOMotorClient
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.config import settings

def init_mongo_client():
    global mongo_client
    mongo_client = AsyncIOMotorClient(
        settings.MONGO_MASTER_HOST,
        maxPoolSize=50,      
        minPoolSize=5,        
        maxIdleTimeMS=30000,
        connectTimeoutMS=5000,
        serverSelectionTimeoutMS=5000,
    )
 
 
def close_mongo_client():
    global mongo_client
    if mongo_client is not None:
        mongo_client.close()
        mongo_client = None


def get_db():
    """
    Returns all collections from the shared client.
    No ping, no new connection — just resolves collection handles.
    """
    db = mongo_client[settings.MONGO_DB_NAME]
    return (
        db[settings.MONGO_LOG_COLLECTION],
        db[settings.MONGO_LEAD_COLLECTION],
        db[settings.MONGO_CRM_COLLECTION],
        db[settings.MONGO_CUSTOMER_CHECK_COLLECTION],
        db[settings.MONGO_SEARCH_DATA_COLLECTION],
    )
 
 
def get_hr_db():
    db = mongo_client[settings.MONGO_DB_NAME]
    return db[settings.MONGO_HR_COLLECTION]

# async def create_mongo_connection(logger):
#     try:
#         agent_col = None
#         lead_agent_col = None
#         cust_col = None
#         crm_col = None
#         histrory_col = None
#         mongo_client = AsyncIOMotorClient(settings.MONGO_MASTER_HOST)
#         response = await mongo_client.admin.command("ping")
#         logger.info(f"Ping Response: {response}")
#         if response.get("ok") == 1:
#             agent_db = mongo_client[settings.MONGO_DB_NAME]
#             agent_col = agent_db[settings.MONGO_LOG_COLLECTION]
#             lead_agent_col = agent_db[settings.MONGO_LEAD_COLLECTION]
#             cust_col = agent_db[settings.MONGO_CUSTOMER_CHECK_COLLECTION]
#             crm_col = agent_db[settings.MONGO_CRM_COLLECTION]
#             histrory_col = agent_db[settings.MONGO_SEARCH_DATA_COLLECTION]
#             logger.info("MongoDB connection is successful")
#         return agent_col, lead_agent_col, crm_col, cust_col, histrory_col
#     except Exception as e:
#         logger.info("Exception in create_mongo_connection_v4 connection!!!")
#         logger.exception(e)
#         return None, None, None, None


# async def create_mongo_connection_hr_agent(logger):
#     try:
#         hr_agent_col = None
#         mongo_client = AsyncIOMotorClient(settings.MONGO_MASTER_HOST)
#         response = await mongo_client.admin.command("ping")
#         logger.info(f"Ping Response: {response}")
#         if response.get("ok") == 1:
#             hr_agent_db = mongo_client[settings.MONGO_DB_NAME]
#             hr_agent_col = hr_agent_db[settings.MONGO_HR_COLLECTION]
#             logger.info("MongoDB connection is successful")
#         return hr_agent_col
#     except Exception as e:
#         logger.info("Exception in create_mongo_connection_hr_agent connection!!!")
#         logger.exception(e)
#         return None

async def create_mongo_connection(logger):
    try:
        agent_col, lead_agent_col, crm_col, cust_col, histrory_col = get_db()
        logger.info("MongoDB collection pool connected")
        return agent_col, lead_agent_col, crm_col, cust_col, histrory_col
    except Exception as e:
        logger.exception(e)
        return None, None, None, None, None
 
async def create_mongo_connection_hr_agent(logger):
    try:
        hr_agent_col = get_hr_db()
        logger.info("MongoDB collection pool connected")
        return hr_agent_col
    except Exception as e:
        logger.exception(e)
        return None


def create_redis_connection(logger):
    try:
        redis_client = redis.StrictRedis(
            host=settings.REDIS_HOST,
            username=settings.REDIS_USERNAME,
            password=settings.REDIS_PASSWORD,
            ssl=True,
            ssl_cert_reqs=ssl.CERT_REQUIRED,
            port=int(settings.REDIS_PORT),
            db=1,
            decode_responses=True,
        )
        response = redis_client.ping()
        if response:
            logger.info("Redis connection successful!!!")
        return redis_client
    except Exception as e:
        logger.info("Exception in redis connection!!!")
        logger.exception(e)
        return None


def create_agent_runtime(logger):
    try:
        session = boto3.Session(region_name=settings.AWS_DEFAULT_REGION)
        agent_runtime_client = session.client("bedrock-agent-runtime")
        logger.info("agent_runtime_client connection successful")
        return agent_runtime_client
    except Exception as e:
        logger.exception(f"exception while establishing agent_runtime_client connection : {e}")
        return None


async def async_convo_log_mongo_insertion(logger, query_input, session_id, mobile_no, response, detected_mobile_no, timestamp, agent_col: AsyncIOMotorCollection):
    try:
        mongo_logger_dict = {
            "user_input": query_input,
            "session_id": session_id,
            "mobile_no": mobile_no,
            "agent_response": response,
            "detected_mobile_no": detected_mobile_no,
            "created_at": timestamp,
        }
        res = await agent_col.insert_one(mongo_logger_dict)
        return {"status": "success", "id": str(res.inserted_id)}
    except Exception as e:
        logger.exception(e)
        return {"status": "error", "message": str(e)}

async def async_convo_faq_mongo_insertion(logger, query_input, languages, session_id, mobile_no, response, detected_mobile_no, timestamp, histrory_col: AsyncIOMotorCollection):
    try:
        mongo_logger_dict = {
            "user_input": query_input,
            "languages": languages,
            "session_id": session_id,
            "mobile_no": mobile_no,
            "agent_response": response,
            "detected_mobile_no": detected_mobile_no,
            "created_at": timestamp,
        }
        res = await histrory_col.insert_one(mongo_logger_dict)
        return {"status": "success", "id": str(res.inserted_id)}
    except Exception as e:
        logger.exception(e)
        return {"status": "error", "message": str(e)}


async def async_hr_log_mongo_insertion(logger, session_id, response, emp_id, mobile_no, timestamp, agent_col: AsyncIOMotorCollection):
    try:
        mongo_logger_dict = {
            "session_id": session_id,
            "mobile_no": mobile_no,
            "employee_id": emp_id,
            "response": response,
            "created_at": timestamp,
        }
        res = await agent_col.insert_one(mongo_logger_dict)
        return {"status": "success", "id": str(res.inserted_id)}
    except Exception as e:
        logger.exception(e)
        return {"status": "error", "message": str(e)}


async def async_lead_log_mongo_insertion(logger, session_id, mobile_no, customer_name, pincode, ID_value, product_type, detected_mobile_no, timestamp, lead_agent_col: AsyncIOMotorCollection):
    try:
        lead_dict = {
            "session_id": session_id,
            "mobile_no": mobile_no,
            "customer_name": customer_name,
            "pincode": pincode,
            "request_id": ID_value,
            "product_type": product_type,
            "detected_mobile_no": detected_mobile_no,
            "created_at": timestamp,
        }
        res = await lead_agent_col.insert_one(lead_dict)
        return {"status": "success", "id": str(res.inserted_id)}
    except Exception as e:
        logger.exception(e)
        return {"status": "error", "message": str(e)}


async def async_crm_log_mongo_insertion(logger, session_id, mobile_no, request, result, timestamp, crm_col):
    try:
        crm_dict = {
            "session_id": session_id,
            "mobile_no": mobile_no,
            "request": request,
            "response": result,
            "created_at": timestamp,
        }
        res = await crm_col.insert_one(crm_dict)
        return {"status": "success", "id": str(res.inserted_id)}
    except Exception as e:
        logger.exception(e)
        return {"status": "error", "message": str(e)}


async def async_cust_log_mongo_insertion(logger, mobile_no, result, timestamp, cust_col):
    try:
        cust_dict = {"mobile_no": mobile_no, "response": result, "created_at": timestamp}
        res = await cust_col.insert_one(cust_dict)
        return {"status": "success", "id": str(res.inserted_id)}
    except Exception as e:
        logger.exception(e)
        return {"status": "error", "message": str(e)}
    
async def fetch_spam(agent_col, query, logger):
    try:
        # Reads recent matching conversations from MongoDB
        # Used for checking spam request detection
        return await agent_col.find(query).to_list(None)

    except Exception as e:
        logger.exception(f"Exception while reading mongo: {e}")
        return None
    
async def get_cust_details_from_mongo(logger, cust_col, mobile_no):
    # Default assumption until verified from DB
    customer_type = "New Customer"
    # Checks whether this mobile number already exists in customer logs
    cursor = cust_col.find({"mobile_no": mobile_no})
    # Fetch only the latest matching document
    cust_doc = await cursor.to_list(length = 1) 
    if(cust_doc is not None and len(cust_doc) >= 1):

        status = cust_doc[0].get('response', {}).get('status')
        # If customer verification already succeeded earlier, marks as existing customer
        if(status == "Success"):
            customer_type = "Existing Customer" 

    return customer_type

async def send_to_lead_api(logger, LEAD_URL, LEAD_URL_TOKEN, api_lead_dict, session_id, mobile_no, crm_col):
    try:
        # Sends captured customer lead details to external CRM/Lead system.
        # aiohttp is used here to avoid blocking the FastAPI event loop.
        async with aiohttp.ClientSession() as session:

            async with session.post(
                LEAD_URL+"?x-api-key="+LEAD_URL_TOKEN,
                headers={'Content-Type': 'application/json'},
                data=json.dumps(api_lead_dict)
            ) as response:

                # Reads CRM API response.
                result = await response.json()

                logger.info(f"Lead Response: {result}")

                return result
                
    except Exception as e:
        logger.exception(f"Exception while sending lead to api: {e}")
        return None

