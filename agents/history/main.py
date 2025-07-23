import pandas as pd
import numpy as np
import redis
import logging
import os
import json
import openai
from dotenv import load_dotenv
from datetime import datetime, timezone
# import required module
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


load_dotenv()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
AGENT_VERSION = "history-agent-v1.0"
STREAM_NAME_IN = "history.in.raw"
STREAM_NAME_OUT = "history.out.raw"
AGENT_VERSION = "history-agent-v1.0"
OPENAI_KEY = os.getenv("OPENAI_KEY", None)
ISRID_COLUMNS = ['Data.Source', 'Incident.Outcome', 'Terrain', 'Subject.Category', 'Subject.Activity', 'Age',
                           'Sex', 'Subject.Status']

last_msg_ID = None
vectorizer = TfidfVectorizer()


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
    logging.info("Read message and parsed correctly")
    return msg_data

def redis_output(standardized_output):
    redis_client.xadd(STREAM_NAME_OUT, {"data": json.dumps(standardized_output)})
    logging.info(f"Summary payload added to {standardized_output} stream")

def normalize_df(df : pd.DataFrame) -> pd.DataFrame:
    logging.info("Normalizing Data")
    columns = ['Data.Source', 'Incident.Outcome', 'Terrain', 'Subject.Category',
       'Subject.Activity', 'Sex', 'Subject.Status']
    for col in columns:
        df[col] = df[col].str.lower()
    df.to_csv('agents/history/isrid2searches4calpoly_output.csv')


def find_match(data : pd.DataFrame, vectorized_rows, queryJSON: dict):
    query_as_string = " ".join(queryJSON.values()).lower()
    query_vectorized = vectorizer.transform([query_as_string])
    similarities = cosine_similarity(query_vectorized, vectorized_rows)[0]
    max_index = np.argmax(similarities)
    return data.iloc[max_index]


def create_summary(match: pd.Series):
    dev_instructions = "You are a Search and Rescue expert tasked with giving summaries of a" \
                    "previous search and rescue incident"
    response = client.responses.create(
        model="gpt-4.1-nano",
        input=[
            {
                "role": "developer",
                "content": dev_instructions
            },
            {
                "role": "user",
                "content": f"Here is a search and rescue incident given in json form {match.to_json()}. Note that the data source value is abbreviated"
            }
        ],
        max_output_tokens = 200,
    )

    content = response.output[0].content[0].text
    
    return content

def main():
    logging.info("Reading Isirid Dataset")
    #key is the input name from redis json and value is column name in the isrid csv
    isrid = pd.read_csv('agents/history/isrid2searches4calpoly_output.csv', index_col=0)
    concatenated_rows = isrid.apply(lambda row: " ".join(row.astype(str)), axis=1)
    vectorized_rows = vectorizer.fit_transform(concatenated_rows)
    logging.info("Start redis channel listening loop")
    while True:
        message_read = redis_input()

        match = find_match(isrid, vectorized_rows, message_read)

        logging.info("Querying LLM")
        summary = create_summary(match)
        metadata = {
            "agent_name": AGENT_VERSION,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "source": {
                "summary-llm": "gpt-4.1-nano"
            }
        }
        standardized_output = {
            "metadata": metadata,
            "summary" : summary
        }
        redis_output(standardized_output)
        



if __name__ == "__main__":
    main()
