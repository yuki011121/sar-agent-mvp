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

#for pub/sub for redis
from shared import wrap_envelope, RedisBus
#using tools, mcp

load_dotenv()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
ISRID_PATH = os.getenv("ISRID_PATH", "isrid2searches4calpoly_output.csv")
AGENT_NAME = "history-agent"
STREAM_NAME_IN = "history.in.raw"
STREAM_NAME_OUT = "history.out.raw"
AGENT_VERSION = "1.1"
OPENAI_KEY = os.getenv("OPENAI_KEY", None)
ISRID_COLUMNS = ['Data.Source', 'Incident.Outcome', 'Terrain', 'Subject.Category', 'Subject.Activity', 'Age',
                           'Sex', 'Subject.Status']
TOP_K_MATCHES = 3
last_msg_ID = None
vectorizer = TfidfVectorizer()
# logger = logging.getLogger(__name__)

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

def redis_output(standardized_output):
    redis_client.xadd(STREAM_NAME_OUT, {"data": json.dumps(standardized_output)})
    logging.info(f"Summary + Action payload added to {STREAM_NAME_OUT} stream")

def normalize_df(df : pd.DataFrame) -> pd.DataFrame:
    logging.info("Normalizing Data")
    columns = ['Data.Source', 'Incident.Outcome', 'Terrain', 'Subject.Category',
       'Subject.Activity', 'Sex', 'Subject.Status']
    for col in columns:
        df[col] = df[col].str.lower()
    df.to_csv(ISRID_PATH)


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

def prompt_llm(matches: pd.DataFrame, query: dict):
    logging.info("Querying LLM")
    NUMBER_OF_TIPS = 3

    #query llm for a summary of the top-k incident matches
    dev_instructions = (
        "You are a Search and Rescue expert. "
        "You have been asked to analyze a set of past incidents that were retrieved because they are similar to a specific search and rescue query. "
        "Your task is to summarize the matched incidents and highlight how they relate to the original query."
    )

    user_instructions = (
        "Task: Summarize the following search and rescue incidents and explain how they relate to the provided query.\n\n"

        "Input Format:\n"
        "- The matching incidents are provided in JSON format, converted from a pandas DataFrame.\n"
        "- The query is a Python dictionary converted to a string.\n"
        "- Each key in the incident JSON is a column name, and its value is a dictionary mapping row indices to cell values.\n\n"

        f"Example:\n"
        '{\n  "location": {"0": "mountain trail", "1": "riverbank"},\n'
        '  "outcome": {"0": "found alive", "1": "not found"}\n'
        '}\n\n'
        
        "Note: Some column values (e.g., data source) may be abbreviated.\n\n"

        f"Query Used:\n{str(query)}\n\n"
        f"Matching Incidents:\n{matches.to_json()}\n\n"

        "Guidelines:\n"
        "- Provide a clear and concise summary of the incidents.\n"
        "- Highlight patterns that are relevant to the query (e.g., terrain, timing, outcome).\n"
        "- Mention any trends or correlations between the incidents and the query.\n"
        "- Do **not** include the incident ID in your summary.\n"
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
        "You are a Search and Rescue expert. Based on the summaries and the original query from a previous conversation, "
        "your task is to provide actionable field recommendations to locate a missing person. "
        "Use your expertise in search patterns, terrain analysis, behavioral profiling, and logistics "
        "to generate specific and practical suggestions tailored to the query context."
    )


    user_instructions = (
        f"Task: Based on the previous summaries and the following search query, give {NUMBER_OF_TIPS} concise and practical "
        "recommendations for conducting a search to locate the missing person.\n\n"

        "Guidelines:\n"
        "- Tailor each tip to the specific query details (terrain, subject profile, etc.).\n"
        "- Include reasoning for each recommendation.\n"
        "- Be specific and actionable.\n"
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
    logging.info(f"Initializing {AGENT_NAME}...")

    try:
        bus = RedisBus(REDIS_URL)
        subGen = bus.subscribe("history", "history-agent", [STREAM_NAME_IN])
    except Exception as e:
        logging.critical(f"Failed to connect to Redis, cannot start agent. Error: {e}")
        return 


    try:
        logging.info("Reading Isirid Dataset")
        #key is the input name from redis json and value is column name in the isrid csv
        isrid = pd.read_csv(ISRID_PATH, index_col=0)
    except FileNotFoundError as e:
        logging.critical(f"Couldn't find CSV dataset file: {e}")
        return
    except Exception as e:
        logging.critical(f"Error reading CSV file: {e}")

    concatenated_rows = isrid.apply(lambda row: " ".join(row.astype(str)), axis=1)
    vectorized_rows = vectorizer.fit_transform(concatenated_rows)
    logging.info("Start redis channel listening loop")

    for message_read in subGen:
        matches = find_match(isrid, vectorized_rows, message_read.payload)
        try:
            summary, actions = prompt_llm(matches, message_read.payload)

            payload = {
                "summary" : summary,
                "actions" : actions
            }

            message_to_publish = wrap_envelope(
                payload=payload,
                source_name=AGENT_NAME,
                source_version=AGENT_VERSION,
                target_stream=STREAM_NAME_OUT
            )

            bus.publish(message_to_publish)
            logging.info(f"Successfully published payload to redis stream {STREAM_NAME_OUT}")
            
        except Exception as e:
            logging.error(f"Error querying llm or publishing to redis: {e}")
        



if __name__ == "__main__":
    main()
