# services/weather_api/app.py
from fastapi import FastAPI
from pydantic import BaseModel
import pathlib, sys

# ensure repo root is importable (so we can import agents.*)
ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# reuse the adapter we already proved works locally
from agents.weather.test_entry import run as weather_run

class In(BaseModel):
    input: str
    context: str | None = None

class Out(BaseModel):
    response: str

app = FastAPI()

@app.get("/healthz")
def health():
    return {"ok": True}

@app.post("/infer", response_model=Out)
def infer(data: In):
    text = weather_run(data.input, data.context or "")
    return Out(response=text)
