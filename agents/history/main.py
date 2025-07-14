import pandas as pd
import redis
import logging
import os
import json

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
AGENT_VERSION = "history-agent-v1.0"
STREAM_NAME_IN = "history.in.raw"
STREAM_NAME_OUT = "history.out.raw"
last_read_id = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

try:
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    logging.info(f"Successfully connected to Redis at {REDIS_URL}")
except redis.exceptions.ConnectionError as e:
    logging.error(f"Could not connect to Redis: {e}")
    exit(1)

def redis_input():
    logging.info("Blocking until a new message is found")
    #blocks until at least one new message is present
    #value returned is in format (stream name, value read)
    input_received = redis_client.blpop([STREAM_NAME_IN], 0)
    #first element returned by redis is the array of values read
    message_read = input_received[1]
    message_read = json.loads(message_read)
    logging.info("Read message and parsed correctly")
    return message_read

def redis_output(output):
    pass

def normalize_df(df : pd.DataFrame):
    logging.info("Normalizing Data")
    columns = ['Data.Source', 'Incident.Outcome', 'Terrain', 'Subject.Category',
       'Subject.Activity', 'Sex', 'Subject.Status']
    for col in columns:
        df[col] = df[col].str.lower()
    df.to_csv('agents/history/isrid2searches4calpoly_output.csv')


def main():
    logging.info("Reading Isirid Dataset")
    #key is the input name from redis json and value is column name in the isrid csv
    mapping_inputs_cols = {"source": 'Data.Source',
                           'outcome': 'Incident.Outcome',
                           'terrain': 'Terrain',
                           'category': 'Subject.Category',
                           'activity': 'Subject.Activity',
                           'age': 'Age',
                           'sex': 'Sex',
                           'status': 'Subject.Status'
                           }
    isrid = pd.read_csv('agents/history/isrid2searches4calpoly_output.csv')
    #normalize_df(isrid)

    logging.info("Start redis channel listening loop")
    while True:
        message_read = redis_input()

        logging.info("Querying dataframe")

        logging.info("Querying LLM")

        standardized_output = {

        }
        redis_output(standardized_output)



if __name__ == "__main__":
    main()

    #gemni flash free version, chatgpt edu