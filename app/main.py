from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from .store import init_db, search_documents, count_documents, all_documents
from .scraper import crawl
from .llm import answer
from .config import INGEST_TOKEN, APP_NAME, MAX_CONTEXT_CHARS

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title=APP_NAME, version="1.0.0", lifespan=lifespan)

class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=1200)

@app.get("/", response_class=HTMLResponse)
def home():
    return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")

@app.get("/health")
def health():
    return {"status": "ok", "documents": count_documents()}

@app.get("/api/sources")
def sources():
    docs = all_documents()
    return {"count": len(docs), "sources": [{"title": d["title"], "url": d["source"], "brand": d["domain"], "fetched_at": d["fetched_at"]} for d in docs]}

@app.post("/api/chat")
async def chat(req: ChatRequest):
    hits = search_documents(req.message, limit=6)
    if not hits:
        return {"answer": "I couldn't find relevant information in the currently indexed public pages. Try a more specific query, or refresh the source data.", "sources": []}
    context_parts, source_list = [], []
    for i, d in enumerate(hits, 1):
        context_parts.append(f"[{i}] Brand: {d['domain']}\nTitle: {d['title']}\nURL: {d['source']}\nContent: {d['content'][:2600]}")
        source_list.append({"id": i, "brand": d["domain"], "title": d["title"], "url": d["source"]})
    context = "\n\n".join(context_parts)[:MAX_CONTEXT_CHARS]
    try:
        response = await answer(req.message, context)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenRouter request failed: {str(exc)[:240]}")
    return {"answer": response, "sources": source_list}

@app.post("/api/ingest")
def ingest(x_ingest_token: str = Header(default="")):
    if not INGEST_TOKEN or x_ingest_token != INGEST_TOKEN:
        raise HTTPException(status_code=401, detail="Valid INGEST_TOKEN required")
    return crawl()
