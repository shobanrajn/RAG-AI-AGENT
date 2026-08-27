import json
from app.core.config import settings
import redis
import ssl

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

def append_data(logger, redis_client, redis_key_name, data, n):
    try:
        for _ in range(n):
            item = redis_client.lpop(redis_key_name)
            if item is None:
                break
            data.append(item)
        return data
    except Exception as e:
        logger.exception(f"Exception in appending data in redis..... {e}")
    
        
def retrieve_data_redis(redis_client, redis_key_name, logger):
    data = [] 
    resp = []
    rem_flag = 0
    count = 0
    try:
        logger.info("Inside redis retrieval.......\n")
        if(redis_client.exists(redis_key_name)):
            count = redis_client.llen(redis_key_name)
            logger.info(f"Redis count....... {count}\n")
            if(count > 0):
                if(count >= 30):
                    rem_flag = 1
                    data = append_data(logger, redis_client, redis_key_name, data, 30)
                else:
                    data = append_data(logger, redis_client, redis_key_name, data, count)
                if(data is not None and len(data) > 0 and isinstance(data[0],str)):
                    for i in range(0,len(data)):
                        resp.append(json.loads(data[i])) 
        logger.info(f'response : {resp} \n resp_count : {count} \n rem_flag : {rem_flag}')
        return resp, count, rem_flag
    except Exception as e:
        logger.exception(f"Exception in retrieving data in redis..... {e}")
        logger.info(f'response : {resp} \n resp_count : {count} \n rem_flag : {rem_flag}')
        count = 0
        return resp, count, rem_flag
        

def create_ans_dict(redis_client, redis_key_name, response, logger):
    resp = []
    rem_flag = 0
    count = 0
    try:
        if(len(response) > 0):
            for ind in range(len(response)):
                logger.info(f"Redis index....... {ind}\n")     
                logger.info(f"Redis response....... {response[ind]}\n")
                logger.info(f"Redis client....... {redis_client}\n")
                logger.info(f"Redis key name....... {redis_key_name}\n")
                redis_resp = redis_client.rpush(redis_key_name, json.dumps(response[ind]))
                logger.info(f"Redis push response....... {redis_resp}\n")
                logger.info(f"Redis client exist....... {redis_client.exists(redis_key_name)}\n")
                redis_client.expire(redis_key_name, 86400)
        resp, count, rem_flag = retrieve_data_redis(redis_client, redis_key_name, logger)
        logger.info("Inside redis injestion.......\n")
        logger.info(f'response : {resp} \n resp_count : {count} \n rem_flag : {rem_flag}')
        return resp, count, rem_flag
    except Exception as e:
        logger.exception(f"Exception in ingesting data in redis..... {e}")
        return resp, count, rem_flag
        
        
    
