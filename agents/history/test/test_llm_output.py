import os
from dotenv import load_dotenv
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.metrics import GEval
from shared import wrap_envelope, RedisBus
from sentence_transformers import SentenceTransformer
import sys
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ApiException
from deepeval.metrics.g_eval import Rubric

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import find_match, qdrant_query, qdrant_ISRID_filter


load_dotenv()
#ephmeral?????
OPENAI_TEST_KEY = os.getenv("OPENAI_TEST_KEY", None)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
#REST api port for qdrant
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", None)
AGENT_NAME = "history-agent"
STREAM_NAME_IN = "history.in.raw"
STREAM_NAME_OUT = "history.out.raw"
AGENT_VERSION = "3.0.0"
QDRANT_TOP_K = 2


if OPENAI_TEST_KEY is None:
    print("openAI api test key is needed to run this test")
    exit(1)


os.environ["OPENAI_API_KEY"] = OPENAI_TEST_KEY


try:
    bus = RedisBus(REDIS_URL)
    #listing for the agents output
    subGen = bus.subscribe("history", "history-agent", [STREAM_NAME_OUT])
except Exception as e:
    print.critical(f"Failed to connect to Redis, cannot start agent. Error: {e}")
    exit(1)

try:
    sentence_transformer = SentenceTransformer('all-MiniLM-L6-v2')
    print("Successfully loaded sentence transformer model")
except Exception as e:
    print(f"Error loading sentence transformer model: {e}")
    exit(1)

try:
    client_Qdrant = QdrantClient(url=QDRANT_URL)
    print(f"Successfully connected to Qdrant at {QDRANT_URL}")
except ApiException as e:
    print(f"Exception when calling QdrantClient: {e}")
    exit(1)
except Exception as e:
    print(f"Could not connect to Qdrant: {e}")
    exit(1)

#publish payload to the agent ot analyze the agent's output
payload = {
        'outcome': 'search',
        'terrain': 'mountainous',
        'category': 'hiker',
        'filter': {
            'type': 'location',
            'filter_value': "us-ky"
        },
        'additional': "This person might have dementia and is likes to go to common spaces when wandering"
}
message_to_publish = wrap_envelope(
    payload=payload,
    source_name=AGENT_NAME,
    source_version=AGENT_VERSION,
    target_stream=STREAM_NAME_IN
)
bus.publish(message_to_publish)

#get agent output
agent_output = next(subGen)
agent_summary = agent_output.payload["summary"]
agent_actions = agent_output.payload["actions"]

#get retrieved context used for querying the llm to generate the actions
incident_Info = payload["additional"]
#copied from history agent main.py
qdrant_context_embedding = sentence_transformer.encode(agent_summary + 
                                                        f"\n {incident_Info}" +"\n Where to locate a missing person based on the summary above.").tolist()
additional_context = qdrant_query(qdrant_context_embedding, QDRANT_COLLECTION, QDRANT_TOP_K)
#build retrieved context used by history agent
additional_context = [context.payload["content"] for context in additional_context]
additional_context.append(agent_summary)
additional_context.append(incident_Info)
    


#setup eval for the agent output
NUMBER_OF_TIPS = 3

user_instructions = (
    f"Task: Based on the previous summaries and the following search query, give {NUMBER_OF_TIPS} concise and practical "
    "recommendations for conducting a search to locate the missing person.\n\n"
)

llm_input = user_instructions
test_case = LLMTestCase(input=llm_input, actual_output=agent_actions, retrieval_context=additional_context)
coherence_metric = GEval(
    name="SAR Faithfulness",
    evaluation_steps = [
        "Extract the actions from the actual output.",
        "Make sure that each action provides an effective task towards finding a missing person.",
        f"It actions should be catered towards the person mentioned in this JSON payload {payload}."
        "Penalize anything that is vague or unclear."
        "Penalize actions that aren't backed up with a reason for them."
        "Penalize the actions contradicting the the retrieval context"
        "Ensure that provenance is given for actions."
        "Give reasons for faithfulness score and make sure actions are using retrieved context."
    ],
    evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.RETRIEVAL_CONTEXT],
    rubric=[
        Rubric(score_range=(0,4), expected_outcome="Poor/Misuse of context and bad actions"),
        Rubric(score_range=(5,7), expected_outcome="Acceptable actions and some usage of context"),
        Rubric(score_range=(8,9), expected_outcome="Good context usage and good actions"),
        Rubric(score_range=(10,10), expected_outcome="Excellent usage of retrieval context and effective actions."),
    ],
    verbose_mode=True,
    model="gpt-4.1-nano"
)

coherence_metric.measure(test_case)
print(coherence_metric.score)
print(coherence_metric.reason)
