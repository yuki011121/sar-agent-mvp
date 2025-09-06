## DockerFile
The docker file assumes that the build context is the SAR-AGENT-MVP directory

The pyproject.toml imports the <i>shared files</i> from the [repo](https://github.com/RandomCyberCoder/Agentic-MVP-Shared) as the package <i>shared</i>.

## History Agent
The agent will take in a query incident and find the top three most similar incidents. The top-k similarities are found using cosine similarity and TF-IDF. The most similar incidents are passed to an llm to generate a summary of them. Next the summaries and query incident are passed back to the LLM to generate actions that can lead to finding the missing person in the query incident.


## Data
The agent requires the cleaned ISRID data set in a CSV format to recall past incidents. This should be the header of the CSV ",Data.Source,Incident.Outcome,Terrain,Subject.Category,Subject.Activity,Age,Sex,Subject.Status". The ISRID dataset give us information on past incidents and the outcomes of those incidents so the agent can use past incidents as a guide for what has or hasn't worked in past search and rescue (SAR) incidents.

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

## Upcoming features and future work
Currently I'm working on figuring out how to build a vector database with Search and Rescue information that can be used to build on top of the current RAG Model that takes past similar incidents in order to create better suggested actions for finding a missing person

There is also the need to add options to the agent to allow for extra information to be passed in. For example, mental state of the person or health conditions (Known impairment or medical conditions) that can be crucial when curating what the most important actions are for finding a missing person.