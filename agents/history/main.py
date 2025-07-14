import pandas as pd
import redis
import logging
import os

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
    #reads the oldest message (switch to $ for newest), limit 1 message to fetch, block forever until
    #a message is received 
    input_received = redis_client.xread({STREAM_NAME_IN: '$'}, count=1, block=0)
    #first element returned by redis is the array of values read
    messages_read = input_received[0]
    input_received_entry = messages_read[1]
    print(input_received)
    return input_received_entry

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
        input_received_entry = redis_input()

        logging.info("Querying dataframe")

        logging.info("Querying LLM")

        standardized_output = {

        }
        redis_output(standardized_output)



if __name__ == "__main__":
    main()

    #gemni flash free version, chatgpt edu