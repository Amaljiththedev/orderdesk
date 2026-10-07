"""One real call to check the key and models work:  python -m app.llm.smoke"""
from app.db.session import SessionLocal
from app.llm.adapter import chat_json

with SessionLocal() as db:
    r = chat_json(db, system="Reply with JSON only.", user='Return {"hello": "world"}',
                  purpose="smoke", prompt_version="smoke-1", max_tokens=50)
    print(r)
