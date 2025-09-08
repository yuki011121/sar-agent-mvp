## DockerFile
The docker file assumes that the build context is the SAR-AGENT-MVP directory

## Other info
The pyproject.toml imports the <i>shared files</i> from the [repo](https://github.com/RandomCyberCoder/Agentic-MVP-Shared) as the package <i>shared</i>.

Expected qdrant setup can be found at this [repo](https://github.com/RandomCyberCoder/vectorDB-Agentic-SAR).

## History Agent
The agent will take in a query incident and find the top three most similar incidents. The top-k similarities are found using cosine similarity and TF-IDF. The most similar incidents are passed to an llm to generate a summary of them.

After the summaries are generated, they are embedded to the sentence-transformer all-MiniLM-L6-v2 to capture semantic meaning. The embedded vector is then used to query the qdrant database to get additional context that will be used in the next step.

Next the summaries, context from qdrant, and query incident are passed back to the LLM to generate actions that can lead to finding the missing person in the query incident.

Overall, a RAG model is used to create actions that will lead to finding a missing person. The RAG model gets context from two sources, the ISIRD dataset and the qdrant vector DB.

## Data
The agent requires the cleaned ISRID data set in a CSV format to recall past incidents. This should be the header of the CSV ",Data.Source,Incident.Outcome,Terrain,Subject.Category,Subject.Activity,Age,Sex,Subject.Status". The ISRID dataset give us information on past incidents and the outcomes of those incidents so the agent can use past incidents as a guide for what has or hasn't worked in past search and rescue (SAR) incidents.


## qdrant
The points returned by the qdrant query have a payload property with the following structure:
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
- ISRID_PATH
    - Path to the cleaned ISRID dataset file. <b>Note</b> this file is not included
    - Optional 
        - If not included it assumes that the path is "isrid2searches4calpoly_output.csv"
- QDRANT_COLLECTION
    - Needed to query collection in qdrant vector DB
    - <b>Required</b>
- QDRANT_URL
    - URL to qdrant REST Api
    - Optional
        - Default "http://localhost:6333"

## Upcoming features and future work

There is also the need to add options to the agent to allow for extra information to be passed in. For example, mental state of the person or health conditions (Known impairment or medical conditions) that can be crucial when curating what the most important actions are for finding a missing person.