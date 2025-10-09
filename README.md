# SAR Agent Integration - Complete System

All 7 SAR agents are now successfully integrated into a unified Redis + MCP A2A system:

### **Integrated Agents**
- **Weather Agent** - Produces weather forecasts
- **Health Agent** - Assesses medical risks and health conditions  
- **History Agent** - RAG-powered historical case analysis
- **Logistics Agent** - Manages resource requests and allocation
- **Path Analysis Agent** - Analyzes terrain and search areas
- **Photo Analysis Agent** - Processes images with YOLO detection
- **Interview Agent** - Analyzes witness interviews and transcripts

### **Architecture Changes**

#### **1. External Shared Package**
- **Before**: Local `shared/` folder with utilities
- **After**: External Git package `agentic-mvp-shared`
- **Import Change**: `from shared import RedisBus, wrap_envelope`

<!-- #### **2. Redis Stream Architecture**
All agents now communicate via standardized Redis streams:
```
Input Streams:
- history.in.raw
- interview.in.raw
- mission.new
- field.observation.raw

Output Streams:
- weather.forecast.raw
- health.assessment.raw
- history.out.raw
- logistics.requests.raw
- path.analysis.raw
- photo.analysis.raw
- interview.analysis.raw
``` -->

#### **2. MCP A2A Messaging**
All agents use standardized message envelopes:
```python
from shared import wrap_envelope, RedisBus

# Publishing messages
message = wrap_envelope(
    payload=data,
    source_name="agent-name",
    source_version="1.0",
    target_stream="output.stream.raw"
)
bus.publish(message)
```

### **Key Technical Updates**

#### **Dependencies Added**
```toml
# New dependencies in pyproject.toml
ultralytics = "^8.1.0"           # YOLO models
sentence-transformers = "^5.1.0" # RAG embeddings
qdrant-client = "^1.15.1"        # Vector database
agentic-mvp-shared = {git = "https://github.com/RandomCyberCoder/Agentic-MVP-Shared.git"}
tf-keras = "^2.20.1"             # Keras compatibility
```

#### **Environment Variables**
```bash
# Required environment variables
OPENAI_API_KEY=your_openai_key
GOOGLE_API_KEY=your_google_key
QDRANT_COLLECTION=SAR_context
```

#### **Services Running**
- **Redis**: Message bus and stream management
- **Qdrant**: Vector database for RAG functionality
- **All Agents**: Running and producing data

### **System Verification**

#### **Check Agent Status**
```bash
# Verify all agents are running
poetry run python -m agents.weather.main &
poetry run python -m agents.health.main &
poetry run python -m agents.history.main &
poetry run python -m agents.logistics.main &
poetry run python -m agents.path_analysis.main &
poetry run python -m agents.photo_analysis.main &
poetry run python -m agents.interview.main &
```

#### **Monitor Redis Streams**
```bash
# Check all active streams
docker exec -it sar-agent-mvp-redis-1 redis-cli
XLEN weather.forecast.raw
XLEN health.assessment.raw
XLEN history.out.raw
XLEN logistics.requests.raw
XLEN path.analysis.raw
XLEN photo.analysis.raw
XLEN interview.analysis.raw
```



#### **Import Changes**
```python
# OLD (local shared folder)
from shared.redis_bus import RedisBus
from shared.a2a_envelope import wrap_envelope

# NEW (external package)
from shared import RedisBus, wrap_envelope
```



    

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