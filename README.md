# Update: New `shared` Folder + Agent Standardization
I've added a **`shared/` folder** with two new core modules and updated **Weather Agent** to use `shared/a2a_envelope.py` for publishing.

## shared/a2a_envelope.py: A2A wrapper 
function `wrap_envelope()` will put every message into a validated `envelope + payload` shape.  
All agents publish Redis entries like:<br/>`{"body": "<json-stringified StandardMessage>"}` |

## shared/mcp_tools.py: MCP helper
 It will help any agent that calls an LLM with tool-calling. <br/>`create_tool_use_request()` builds the request, `get_tool_call_from_response()` extracts `(tool_name, args)` from the reply. Supports OpenAI (`gpt-4.1-nano` default) and Gemini (`gemini-1.5-flash` default).
 
## Todo

- If your agent publishes to Redis → integrate A2A from `shared/a2a_envelope.py`
- If your agent uses LLMs (e.g., `history analysis`, `health`)→ integrate both A2A + MCP from `shared/`.
- Check the code comments in a2a_envelope.py and mcp_tools.py for usage examples
## Steps to Integrate
#### 1. Switch to your feature branch:
   ```
   git switch feature/history
   ```
#### 2. Merge the latest dev into your branch
This will bring the new shared/ folder into your branch.
   ```
git merge dev
   ```
#### 3. Resolve conflicts
You will likely see a conflict in:
```
agents/weather/main.py
```
This is because dev has the refactored Weather Agent using the new shared utils.


If using VS Code:   
Click “Accept Incoming Changes” for agents/weather/main.py

#### 4. Adapt your own agent
Now your branch has:
```
shared/a2a_envelope.py
shared/mcp_tools.py
```
Update your history-analysis-agent/main.py:   
Use wrap_envelope() from a2a_envelope to publish Redis messages
and use create_tool_use_request(), get_tool_call_from_response() from mcp_tools.  
#### 5. Commit your merge result    
    
    

# SAR Multi-Agent MVP
A functional AI-powered multi-agent search and rescue prototype.

## Please Read Before Pushing Code

To avoid conflicts and keep the codebase organized, **do not push your code directly to the `dev` branch**.
Instead, please work on your own feature branch and submit a **Pull Request** to `dev`.
### Example Workflow
#### 1. Pull the latest `dev` branch:
   ```
   git checkout dev
   git pull origin dev
   ```
#### 2. Create your own feature branch from dev:
   ```
git checkout -b feature/photo-agent
   ```
#### 3. Make changes, commit, and push to your branch:
```
git add .
git commit -m "Implement basic object detection"
git push origin feature/photo-agent
```
#### 4. When you're done, open a Pull Request to merge into dev. 
## Quick Start
### 1. Prerequisites

Make sure you have the following installed:

- **Git** 
- **Docker** 
- **Python 3.10+** and **Poetry** 


### 2. Setup

We provide two ways to set up the environment:  
Use the script for convenience, or follow manual steps if you prefer more control.

#### The Easy Way 

Run the setup script from the project root. It will check for dependencies, start services, and install Python packages.

```
git clone https://github.com/yuki011121/sar-agent-mvp
cd sar-agent-mvp
chmod +x setup.sh
./setup.sh
```

#### The Manual Way
```
docker compose up -d
poetry env use python3
poetry install
```
### 3. Running an Agent
Example: run the Weather Agent.
```
source "$(poetry env info --path)/bin/activate"
poetry run python -m agents.weather.main
```

### 4. Check Redis
Open a new terminal window and run the following commands:
```
docker exec -it sar-agent-mvp-redis-1 redis-cli
XLEN weather.forecast.raw
XREVRANGE weather.forecast.raw + - COUNT 1
```
The second command shows the total number of entries in the weather.forecast.raw stream.
The third command retrieves the most recent entry from that stream.

### Troubleshooting
- SolverProblemError during poetry install or poetry add
This is a dependency version conflict. Our project has a specific Python requirement because of the pyautogen library.
Solution: Open the pyproject.toml file and ensure your project's Python version is set to python = ">=3.10, <3.14". Your system's base python3 must also fall within this range.
- ModuleNotFoundError (e.g., No module named 'redis'): This usually means the virtual environment is corrupted or out of sync. A reliable fix is to rebuild it:
```
# 1. Remove the old environment
poetry env remove python
# 2. Re-install everything from scratch
poetry install
```