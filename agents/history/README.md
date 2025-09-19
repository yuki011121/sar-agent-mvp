
# History Agent

### Overview

The History agent will take in a query incident and use a RAG model to provide summaries of past similar incidents and actions that will
help locate the person in the query incident. The agent includes options to filter past incidents either by location, age, or category and 
allows additional info about the incident to be passed in.

### Deeper Dive
The agent will take in a query incident and find the top three most similar incidents. There is also the option to filter the incidents that are searched by either location, age range, or category. If filtering results in no past incidents being found then it will retry the search without filtering. The top-k similar past incidents are found using cosine similarity and TF-IDF. The TF-IDF model is saved in the "models" directory which will be loaded in by the agent when it is spun up. It is assumed that the past incidents are stored in Qdrant. Read the Qdrant section below for setup information. The most similar incidents are passed to an llm to generate a summary of them. This is used as context for generating actions.

After the summaries are generated, the summaries are concatenated with any additional info passed through the "additonal" option, and they are embedded using a sentence-transformer (all-MiniLM-L6-v2) to capture semantic meaning. The embedding is then used to query the Qdrant database to get additional context that will be used in the next step.

Next the summaries, context from Qdrant, and additional info (from the "additional" option) are passed back to the LLM to generate actions that can lead to finding the missing person in the query incident.



## DockerFile
The docker file assumes that the build context is the SAR-AGENT-MVP directory


## Agent Data Input Contract
Expected agent payload format and example
````JSON
{
  "Data_Source": "nz",
  "Incident_Outcome": "family friend",
  "Terrain": "flat",
  "Subject_Category": "child",
  "Subject_Activity": "playing",
  "Age": 11,
  "Sex": "f",
  "Subject_Status":"well",
  "filter": {
    "type": "location: str | age: float/int | category: str",
    "value": "<value for type>"
  },
  "additional": "<additional info>"
}
````

Valid values for the properties (not including the last two) are those that comply to the ISRID data set by Robert Koester.

Not al properties need to be included. The "filter' and "additional" properties are options. The other ones are used to query for past incidents and don't all have to be included. However, the more of those properties you included, the more relevant the retrieved past incidents will be.


## Qdrant Usage
### Past Incidents collection
The history agent assumes that the past incidents are in a Qdrant collection called "ISRID_collection". A script called isrid_parsing.py is included that can be ran and will automatically create and populate the collection provided a cleaned version of the ISRID dataset is given with the following headeer ",Data.Source,Incident.Outcome,Terrain,Subject.Category,Subject.Activity,Age,Sex,Subject.Status". An example of the payload associated to a point in the database is shown below.
````json
{
  "provenance": {
    "source":"ISRID Dataset",
    "author":"Bob Koester"
    },
  "content": "nz family friend flat child playing 11 f well", 
  "metadata": {
    "Data_Source":"nz",
    "Incident_Outcome":"family friend",
    "Terrain":"flat",
    "Subject_Category":"child", 
    "Subject_Activity":"playing",
    "Age":11,
    "Sex":"f",
    "Subject_Status":"well"
  }
}
````

### SAR context collection
The SAR context should all be stored in the same collection. The name of this collection should be store in the environment variable called "QDRANT_COLLECTION". Every point in this collection should have the format specified below for its payload. This is important so attribution can be given and the content associated with the embedding can be retrieved to be used in the RAG model. Furthermore the content should be embedded using the embedding model "all-MiniLM-L6-v2".
````json
{
  "provenance": {
    "source": "<source of content>",
    "author": "<authors of source>"
  },
  "content": "<content that generated embedding>"
}
````

## .env
- OPENAI_KEY
    - <b>Required</b>
    - Needed for OpenAI api
- REDIS_URL
    - URL to connect to Redis
    - URL Schemes supported "redis://", "rediss://", "unix://". More info [here](https://redis.readthedocs.io/en/latest/connections.html)
    - Optional
        - If not included this will default to "redis://localhost:6379"
- QDRANT_COLLECTION
    - Needed to query collection in qdrant vector DB for SAR context
    - <b>Required</b>
- QDRANT_URL
    - URL to qdrant REST Api
    - Optional
        - Default "http://localhost:6333"
- OPENAI_TEST_KEY
    - openAI api key used for testing
    - Optional
        - feel free to use the same key as the OPENAI_KEY variable

## Testing
Two files are included in the ``test`` directory. The ``test_llm_output.py`` file is used for end to end testing using GEval to evaluate if the llm outputs are sound and utilize the retrieved context properly. The ``test_agent.py`` file is used to test the Qdrant database and ensures that the filtering used by the agent works as expected.

## Other info
The pyproject.toml imports the <i>shared files</i> from the [repo](https://github.com/RandomCyberCoder/Agentic-MVP-Shared) as the package <i>shared</i>.

Expected qdrant setup can be found at this [repo](https://github.com/RandomCyberCoder/vectorDB-Agentic-SAR). It includes some example scripts for uploading data to Qdrant and querying Qdrant

Files containing the data the goes into the Qdrant is unfortunately not included due to NDA's