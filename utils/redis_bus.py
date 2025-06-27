# utils/redis_bus.py
import json, os, redis, uuid, datetime as dt

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

def publish(stream_name: str, payload: dict, msg_type="message", sender="default-agent"):
    """Publishes a message envelope to a given Redis Stream."""
    envelope = {
        "id": str(uuid.uuid4()),
        "type": msg_type,
        "sender": sender,
        "payload": payload,
        "ts": dt.datetime.utcnow().isoformat() + "Z",
    }
    r.xadd(stream_name, {"json": json.dumps(envelope)})
    print(f'>> Published message {envelope["id"]} to stream {stream_name}')