import logging
import os
from google import genai
from dotenv import load_dotenv
# import required module
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ApiException
from sentence_transformers import SentenceTransformer
import ast
from typing import List, Optional
from qdrant_client.http.models.models import ScoredPoint
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range
from joblib import load
#for pub/sub for redis
from shared import wrap_envelope, RedisBus

load_dotenv()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
#REST api port for qdrant
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", None)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", None)
AGENT_NAME = "history-agent"
STREAM_NAME_IN = "history.in.raw"
STREAM_NAME_OUT = "history.out.raw"
AGENT_VERSION = "3.0.0"
TOP_K_MATCHES = 3
QDRANT_TOP_K = 2
QDRANT_ISRID_COLLECTION = "ISRID_collection"
ISRID_VECTORIZER_PATH = "agents/history/models/isrid_tfidf_vectorizer.joblib"


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


if GOOGLE_API_KEY is None:
    logging.info("Couldn't find a api key for OPENAI")
    exit(1)

if QDRANT_COLLECTION is None:
    logging.info("Couldn't find a collection name for QDRANT")
    exit(1)

client_gemini = genai.Client(api_key=GOOGLE_API_KEY)

try:
    client_Qdrant = QdrantClient(url=QDRANT_URL,
                                 api_key=QDRANT_API_KEY)
    logging.info(f"Successfully connected to Qdrant at {QDRANT_URL}")
except ApiException as e:
    logging.critical(f"Exception when calling QdrantClient: {e}")
    exit(1)
except Exception as e:
    logging.critical(f"Could not connect to Qdrant: {e}")
    exit(1)

try:
    sentence_transformer = SentenceTransformer('all-MiniLM-L6-v2')
    logging.info("Successfully loaded sentence transformer model")
except Exception as e:
    logging.critical(f"Error loading sentence transformer model: {e}")
    exit(1)

try:
    ISRID_VECTORIZER = load(ISRID_VECTORIZER_PATH)
    logging.info("Successfully loaded ISRID vectorizer")
except Exception as e:
    logging.critical(f"Error loading ISRID vectorizer: {e}. Fix by running isrid_parsing.py")
    logging.critical(f"Make sure the path {ISRID_VECTORIZER_PATH} is correct" +  
                     " or run agents/history/isrid_parsing.py to create it.")
    exit(1)


def qdrant_ISRID_filter(query_filter: dict) -> List[FieldCondition]:
    filters = []

    try:
        query_filter["type"] = query_filter["type"].lower()
        if query_filter["type"] == "category":
            filters.append(FieldCondition(key="metadata.Subject_Category"
                                        , match=MatchValue(value=query_filter["filter_value"])))
        elif query_filter["type"] == "age":
            age_target = float(str(query_filter["filter_value"]))
            #grow delta for age range as age grows. fixed below a 10 years old
            delta = 1 if age_target < 10 else age_target * 0.1
            filters.append(FieldCondition(key="metadata.Age"
                                        , range=Range(
                                            gt = None,
                                            gte = age_target - delta,
                                            lt = None,
                                            lte = age_target + delta
                                        )))
        elif query_filter["type"] == "location":
            filters.append(FieldCondition(key="metadata.Data_Source"
                                        , match=MatchValue(value=query_filter["filter_value"])))
            
    except Exception as e:
        logging.error(f"Problem making filter for Qdrant ISRID query. Error: {e}")



    return filters

def find_match(queryJSON: dict) -> list[dict]:
    # Convert queryJSON to a string and then to a vector
    query_filter = queryJSON["filter"] if "filter" in queryJSON else None
    queryJSON.pop('filter', None)
    queryJSON.pop('additional', None)
    query_as_string = " ".join(queryJSON.values()).lower()
    query_vector = ISRID_VECTORIZER.transform([query_as_string]).toarray()[0]

    if query_filter:
        top_matches = qdrant_query(query_vector, QDRANT_ISRID_COLLECTION, TOP_K_MATCHES
                                   , qdrant_ISRID_filter(query_filter))
        
        #if we couldn't find any points with the filter then search the entire database
        if len(top_matches) == 0:
            top_matches = qdrant_query(query_vector, QDRANT_ISRID_COLLECTION, TOP_K_MATCHES)
    else:
        top_matches = qdrant_query(query_vector, QDRANT_ISRID_COLLECTION, TOP_K_MATCHES)
    
    formatted_matches = [match.payload["metadata"] for match in top_matches]
    
    return formatted_matches


def verify_llm_response(status: str) -> None:
    if status != "completed":
        raise Exception(f"Couldn't evaluate llm_resonse due to it being in a non-completed state. LLM response state: {status}")


def clean_llm_output(text: str) -> str:
    """
    Cleans LLM output text by decoding escape sequences and UTF-8 byte strings.
    Useful before creating embeddings.
    """
    try:
        # First pass: decode escape sequences (e.g. \\n -> \n)
        text = ast.literal_eval(f'"{text}"')
    except Exception:
        pass  # Skip if it's already a properly escaped string

    try:
        # Second pass: decode UTF-8 bytes (e.g. \xe2\x80\x94 -> —)
        text = text.encode('utf-8').decode('unicode_escape').encode('latin1').decode('utf-8')
    except Exception:
        pass  # Skip if not needed

    text = text.replace("**", "")
    return text


def qdrant_query(query_vector: List[float], collection_name: str, results_limit: int
                 , filter: Optional[List[FieldCondition]] = None) -> List[ScoredPoint]:
    logging.info("Querying Qdrant")
    filter = filter or []
    try:
        search_result = client_Qdrant.query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter = Filter(
                must=filter
            ),
            limit=results_limit,
            with_payload=True
        ).points
        return search_result
    except ApiException as e:
        logging.error(f"Exception when calling QdrantClient for collection {collection_name}: {e}")
        return [] 
    except Exception as e:
        logging.error(f"Error querying Qdrant: {e}")
        return []

def prompt_llm(matches: List[dict], query: dict, incident_Info: str):
    logging.info("Querying LLM")
    NUMBER_OF_TIPS = 3

    query.pop('filter', None)
    query.pop('additional', None)

    #query llm for a summary of the top-k incident matches
    dev_instructions = (
        "You are a Search and Rescue expert. "
        "You have been asked to analyze a set of past incidents that were retrieved because they are similar to a specific search and rescue query. "
        "Your task is to summarize the matched incidents and highlight how they relate to the original query."
        "In the summary make sure you point out anything that seems significant like age or health conditions"
    )

    user_instructions = (
        "Task: Summarize the following search and rescue incidents and explain how they relate to the provided query.\n\n"

        "<context>\n"
        "<input_format>\n"
        "- The matching incidents are a list of python dictionaries converted to JSON. Each dictionary is a separate SAR incident\n"
        "- Each key in the incident dictionary is a relevant piece of information about the incident.\n\n"
        "- Note; that some key-value pairs may be abbreviated (e.g., data source)\n"
        "- The query is a Python dictionary converted to a string.\n"

        f"Example of an incident dictionary (Note: some columns such as data source might co):\n"
        "{'Data.Source': 'nz', 'Incident.Outcome': 'search', 'Terrain': 'mountainous', 'Subject.Category': 'dementia', 'Subject.Activity': 'walkaway', 'Age': '67', 'Sex': 'f', 'Subject.Status': 'well'}"
        
        "Note: Some column values (e.g., data source) may be abbreviated.\n\n"
        "</input_format>\n"

        f"Query Used:\n{str(query)}\n\n"
        f"Matching Incidents:\n{str(matches)}\n"
        "</context>\n\n"
        

        "<guidelines>\n"
        "- Provide a clear and concise summary of the incidents.\n"
        "- Highlight patterns that are relevant to the query (e.g., terrain, timing, outcome).\n"
        "- Mention any trends or correlations between the incidents and the query.\n"
        "- Do **not** include the incident ID in your summary.\n"
        "</guidelines>"
        )

    interaction1 = client_gemini.interactions.create(
        model="gemini-2.5-flash",
        system_instruction=dev_instructions,
        input=user_instructions
    )
    
    verify_llm_response(interaction1.status)
    prev_interactions_response = interaction1.outputs[-1].text

    summary = clean_llm_output(prev_interactions_response)

    qdrant_context_embedding = sentence_transformer.encode(summary + 
                                                           f"\n {incident_Info}" +"\n Where to locate a missing person based on the summary above.").tolist()
    additional_context = qdrant_query(qdrant_context_embedding, QDRANT_COLLECTION, QDRANT_TOP_K)
    additional_context = [context.payload for context in additional_context]
    #query llm for actions to take based on summaries generated
    
    dev_instructions = (
        "You are a Search and Rescue expert. Based on the summaries and the original query from a previous conversation, "
        "your task is to provide actionable field recommendations to locate a missing person. "
        "Use your expertise in search patterns, terrain analysis, behavioral profiling, and logistics "
        "to generate specific and practical suggestions tailored to the query context."
    )


    user_instructions = (
        f"<task>\n Based on the previous summaries and the following search query, give {NUMBER_OF_TIPS} concise and practical "
        "recommendations for conducting a search to locate the missing person. \n</task>\n\n"

        "<guidelines>\n Guidelines:\n"
        "- Tailor each tip to the specific query details (terrain, subject profile, etc.).\n"
        "- Include reasoning for each recommendation.\n"
        "- Be specific and actionable.\n\n"

        "Additional Output Guidelines:\n"
        "- include attribution at the end of the tips section as mentioned in the additional context. \n</guidelines>\n\n"

        "<RAG_context>\n Additional search and rescue (SAR) Context:\n"
        "- This is SAR information that may be useful to consider when generating recommendations\n"
        "- the format of this is a list of dictionaries\n"
        "- Each dictionary is in the format {'provenance': {'source': '', 'author': ''}, 'content': 'relevant information'}\n"
        "- The provenance field gives attribution for the content field. Use the author property to give attribution.\n"
        f"{additional_context}\n\n"

        "Additional Incident Information\n"
        "- Any information in this section is known additional information about the incident\n"
        f"- {incident_Info} \n<RAG_context>"
    )
    
    interaction2 = client_gemini.interactions.create(
        model="gemini-2.5-flash",
        system_instruction=dev_instructions,
        input=user_instructions,
        previous_interaction_id=interaction1.id
    )

    verify_llm_response(interaction2.status)

    actions = clean_llm_output(interaction2.outputs[-1].text)
    # print(f"token usage for interaction1: {interaction1.usage.to_dict()}\n token usage for interaction2: {interaction2.usage.to_dict()}")
    # print(f"Summary: {summary} \n\n\n Actions: {actions}")
    return summary, actions

def main():
    logging.info(f"Initializing {AGENT_NAME}...")

    try:
        bus = RedisBus(REDIS_URL)
        subGen = bus.subscribe("history", "history-agent", [STREAM_NAME_IN])
    except Exception as e:
        logging.critical(f"Failed to connect to Redis, cannot start agent. Error: {e}")
        return 

    logging.info("Start redis channel listening loop")

    
    for message_read in subGen:

        additional_info = message_read.payload.pop('additional', None)
        additional_info = additional_info or ""

        matches = find_match(message_read.payload)
        try:
            summary, actions = prompt_llm(matches, message_read.payload, additional_info)

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
