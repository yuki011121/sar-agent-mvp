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
TOP_K_MATCHES = 3
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
    logging.info(f"Summary + Action payload added to {STREAM_NAME_OUT} stream")

def normalize_df(df : pd.DataFrame) -> pd.DataFrame:
    logging.info("Normalizing Data")
    columns = ['Data.Source', 'Incident.Outcome', 'Terrain', 'Subject.Category',
       'Subject.Activity', 'Sex', 'Subject.Status']
    for col in columns:
        df[col] = df[col].str.lower()
    df.to_csv('agents/history/isrid2searches4calpoly_output.csv')


def find_match(data : pd.DataFrame, vectorized_rows, queryJSON: dict) -> pd.DataFrame:
    query_as_string = " ".join(queryJSON.values()).lower()
    query_vectorized = vectorizer.transform([query_as_string])
    similarities = cosine_similarity(query_vectorized, vectorized_rows)[0]
    max_indexes = np.argsort(similarities)[::-1][:TOP_K_MATCHES]
    return data.iloc[max_indexes]

def verify_llm_response(response):
    if hasattr(response, "error") and response.error is not None:
        code = getattr(response.error, "code", "unknown")
        message = getattr(response.error, "message", "No message provided")
        raise Exception(f"Model error\nCode: {code}\nMessage: {message}")

def prompt_llm(matches: pd.DataFrame):
    logging.info("Querying LLM")
    NUMBER_OF_TIPS = 3

    #query llm for a summary of the top-k incident matches
    dev_instructions = (
        "You are a Search and Rescue expert tasked with analyzing data from past incidents. "
        "Your job is to generate concise summaries of search and rescue incidents based on structured input."
    )

    user_instructions = (
        "Task: Summarize the following search and rescue incidents.\n\n" 
        "Input Format: The data is provided in JSON format, converted from a pandas DataFrame. " 
        "Each key is a column name, and its value is a dictionary where the keys are row indices and the values are the column entries.\n"
        "a dictionary of a row number (the key) to the value for that column.\n" 
        f"Example:\n"
        '{\n  "location": {"0": "mountain trail", "1": "riverbank"},\n'
        '  "outcome": {"0": "found alive", "1": "not found"}\n'
        '}\n\n'
        "Note: that the data source value is abbreviated.\n" 
        f"Content:\n{matches.to_json()}\n\n" 
        "Guidelines:\n"
        "- Summarize the incidents clearly and concisely.\n"
        "- Focus on key patterns (e.g., common terrain, outcomes, conditions).\n"
        "- Do **not** include the incident ID in the summary.\n"
        "Output Format: make the format so i"
    )

    response = client.responses.create(
        model="gpt-4.1-nano",
        input=[
            {
                "role": "developer",
                "content": dev_instructions
            },
            {
                "role": "user",
                "content": user_instructions
            }
        ],
        max_output_tokens = 300,
        previous_response_id = None
    )

    verify_llm_response(response)

    summary = response.output[0].content[0].text

    #query llm for actions to take based on summaries generated

    dev_instructions = (
        "You are a Search and Rescue expert. Based on summaries from a previous conversation, "
        "your task is to provide actionable guidance to help locate a missing person. "
        "Use your knowledge of search patterns, terrain analysis, behavioral profiling, "
        "and logistical coordination to generate relevant suggestions for field teams."
    )

    user_instructions = (
        f"Task: Based on the previous summaries, give {NUMBER_OF_TIPS} concise and practical recommendations "
        "for how to conduct a search to locate a missing person in a similar situation. "
        "Focus on tactics, tools, and reasoning behind the suggestions. Be specific."
    )

    response = client.responses.create(
        model="gpt-4.1-nano",
        input=[
            {
                "role": "developer",
                "content": dev_instructions
            },
            {
                "role": "user",
                "content": user_instructions
            }
        ],
        max_output_tokens = 450,
        previous_response_id = response.id
    )

    verify_llm_response(response)
    
    actions = response.output[0].content[0].text
    
    return summary, actions

def main():
    logging.info("Reading Isirid Dataset")
    #key is the input name from redis json and value is column name in the isrid csv
    isrid = pd.read_csv('agents/history/isrid2searches4calpoly_output.csv', index_col=0)
    concatenated_rows = isrid.apply(lambda row: " ".join(row.astype(str)), axis=1)
    vectorized_rows = vectorizer.fit_transform(concatenated_rows)
    logging.info("Start redis channel listening loop")
    while True:
        message_read = redis_input()

        matches = find_match(isrid, vectorized_rows, message_read)
        try:
            summary, actions = prompt_llm(matches)
            metadata = {
                "agent_name": AGENT_VERSION,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "source": {
                    "summary-llm": "gpt-4.1-nano"
                }
            }
            standardized_output = {
                "metadata": metadata,
                "summary" : summary,
                "actions" : actions
            }
            redis_output(standardized_output)
        except Exception as e:
            logging.error(f"Error querying llm: {e}")
        



if __name__ == "__main__":
    main()
