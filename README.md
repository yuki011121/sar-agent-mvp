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
poetry run python -m agents.weather.main
```

### 4. Check Redis
Open a new terminal window and run the following commands:
```
XLEN weather.forecast.raw
XREVRANGE weather.forecast.raw + - COUNT 1
```
The first command shows the total number of entries in the weather.forecast.raw stream.
The second command retrieves the most recent entry from that stream.

### Troubleshooting
- SolverProblemError during poetry install or poetry add
This is a dependency version conflict. Our project has a specific Python requirement because of the ag2 library.
Solution: Open the pyproject.toml file and ensure your project's Python version is set to python = ">=3.10, <3.14". Your system's base python3 must also fall within this range.
- ModuleNotFoundError (e.g., No module named 'redis'): This usually means the virtual environment is corrupted or out of sync. A reliable fix is to rebuild it:
```
# 1. Remove the old environment
poetry env remove python
# 2. Re-install everything from scratch
poetry install
```