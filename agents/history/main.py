import pandas as pd
import redis
import logging
import os
import json
import openai
from dotenv import load_dotenv


load_dotenv()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
AGENT_VERSION = "history-agent-v1.0"
STREAM_NAME_IN = "history.in.raw"
STREAM_NAME_OUT = "history.out.raw"
OPENAI_KEY = os.getenv("OPENAI_KEY", None)

last_msg_ID = None


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


if OPENAI_KEY is None:
    logging.info("Couldn't find a api key for OPENAI")
    exit(1)

client = openai.OpenAI(api_key=OPENAI_KEY)

try:
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    logging.info(f"Successfully connected to Redis at {REDIS_URL}")
except redis.exceptions.ConnectionError as e:
    logging.error(f"Could not connect to Redis: {e}")
    exit(1)

def redis_input():
    global last_msg_ID
    ID_INDEX = 0
    MSG_DATA_INDEX = 1
    logging.info("Blocking until a new message is found")
    #reads the oldest message (switch to $ for newest), limit 1 message to fetch, block forever until
    #a message is received 
    input_received = redis_client.xread({STREAM_NAME_IN: ('$' if last_msg_ID is None else last_msg_ID)}, count=1, block=0)
    #input_received is an array arrays that contain a key (stream name)
    # and an array of tuples (ID, field-value pairs)
    stream_data = input_received[0]
    msgs_read = stream_data[1]
    #there is only one msg that is read
    msg = msgs_read[0]
    last_msg_ID = msg[ID_INDEX]
    msg_data = msg[MSG_DATA_INDEX]
    print(msg_data)
    logging.info("Read message and parsed correctly")
    return msg_data

def redis_output(output):
    pass

def normalize_df(df : pd.DataFrame) -> pd.DataFrame:
    logging.info("Normalizing Data")
    columns = ['Data.Source', 'Incident.Outcome', 'Terrain', 'Subject.Category',
       'Subject.Activity', 'Sex', 'Subject.Status']
    for col in columns:
        df[col] = df[col].str.lower()
    df.to_csv('agents/history/isrid2searches4calpoly_output.csv')


def find_matches(data : pd.DataFrame, queryJSON: dict):
    logging.info("Querying dataframe")
    map_inputs_cols = {
                            "source": 'Data.Source',
                           'outcome': 'Incident.Outcome',
                           'terrain': 'Terrain',
                           'category': 'Subject.Category',
                           'activity': 'Subject.Activity',
                           'age': 'Age',
                           'sex': 'Sex',
                           'status': 'Subject.Status'
                        }
    
    mask = pd.Series(True, index=data.index)

    for key, col in map_inputs_cols.items():
        if key in queryJSON and pd.notna(queryJSON[key]):
            mask &= data[col] == queryJSON[key]

    return data[mask]


def create_summary():
    instructions = "You are an excellent story teller"
    model_input = "Tell me a three sentence bedtime story about a unicorn."
    response = client.responses.create(
        model="gpt-4.1-nano",
        instructions= instructions,
        input= model_input,
        max_output_tokens = 200,
    )

    # print(type(response))
    # print(response)
    response=response.model_dump()

    if response["error"]:
        print("there was an error with the model response")
        print(response["error"])
        exit(1)
    
    print(response)
    #this is a dictionary
    output = response[output][0]
    #output -> content(array of dictionaries) -> get text string
    summary = output["content"][0]["text"]
    print(summary)
    
    return summary
#coseine similiarty and TF-IDF

def main():
    logging.info("Reading Isirid Dataset")
    #key is the input name from redis json and value is column name in the isrid csv
    isrid = pd.read_csv('agents/history/isrid2searches4calpoly_output.csv', index_col=0)

    logging.info("Start redis channel listening loop")
    while True:
        message_read = redis_input()

        # matches = find_matches(isrid, message_read)
        # print(matches)
        # print(type(matches))
        # print(json.dumps(matches.to_dict()))


        logging.info("Querying LLM")
        #create_summary()

        standardized_output = {

        }
        redis_output(standardized_output)
        



if __name__ == "__main__":
    main()

    #gemni flash free version, chatgpt edu