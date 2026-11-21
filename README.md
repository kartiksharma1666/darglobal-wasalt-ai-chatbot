# Property Intelligence Assistant — DarGlobal × Wasalt

A Dockerized FastAPI + RAG-style real-estate research chatbot. It crawls publicly accessible pages from DarGlobal and Wasalt, indexes extracted text in SQLite, retrieves relevant passages, and sends grounded context to an OpenRouter chat model. Responses include source URLs.

## Architecture
- **UI:** responsive HTML/CSS/JavaScript served by FastAPI
- **API:** FastAPI (`POST /api/chat`, `GET /health`, `GET /api/sources`)
- **Crawler:** Requests via HTTPX + BeautifulSoup; same-domain only, sitemap-first, polite delay
- **Retrieval:** lightweight token-overlap retrieval over SQLite (no heavyweight embedding model required on free hosting)
- **LLM:** OpenRouter OpenAI-compatible Chat Completions API; defaults to `openrouter/free`
- **Container:** Docker
- **Deployment:** Render Docker Web Service

## Important scope / data notes
- Only public HTML pages are collected. The crawler does not bypass login, CAPTCHAs, paywalls, robots restrictions, or access controls.
- Dynamic listing pages may require JavaScript and may not expose every listing to this lightweight crawler. For such pages, the application indexes only text returned in public HTML.
- Property inventory, asking prices, and availability are volatile. Verify them on the linked source page before making decisions.
- DarGlobal's domain and page structure may change. Review `app/scraper.py` and update its `SITES` seeds if needed.
- This is a project prototype, not financial, legal, valuation, or investment advice.
- SQLite on Render's free ephemeral filesystem can reset on redeploy/restart. For persistent production data, attach a paid persistent disk or use managed Postgres. On free Render, re-run ingestion after a reset.

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env            # fill OPENROUTER_API_KEY and INGEST_TOKEN
uvicorn app.main:app --reload
```
Open http://localhost:8000

## Docker
```bash
docker build -t property-assistant .
docker run --rm -p 10000:10000 \\
  -e OPENROUTER_API_KEY=YOUR_KEY \\
  -e INGEST_TOKEN=YOUR_LONG_SECRET \\
  -v property-data:/var/data \\
  -e DATABASE_PATH=/var/data/property_assistant.db \\
  property-assistant
```
Open http://localhost:10000

## Ingest public pages
The ingestion endpoint is protected by `INGEST_TOKEN`:
```bash
curl -X POST http://localhost:8000/api/ingest \\
  -H "X-Ingest-Token: YOUR_LONG_SECRET"
```
It crawls a bounded number of same-domain URLs from each site's sitemap and seed pages. Re-run after deployment to populate the live knowledge base. Check `/api/sources` and `/health`.

## OpenRouter
1. Create an API key at https://openrouter.ai/keys
2. Set `OPENROUTER_API_KEY` in your environment.
3. `OPENROUTER_MODEL=openrouter/free` selects a currently available free chat model. You can pin a specific free model ID from https://openrouter.ai/collections/free-models if preferred.
4. Free model availability and rate limits vary by provider and can change. The app handles provider errors by returning an API error; check OpenRouter dashboard/model page if a provider is unavailable.

## Deploy to Render
1. Push this folder to a new GitHub repository.
2. In Render, choose **New → Web Service**, connect the repository, and select **Docker** as the runtime.
3. Render detects `Dockerfile`; keep the default Docker command.
4. Add environment variables:
   - `OPENROUTER_API_KEY` = your OpenRouter key (secret)
   - `OPENROUTER_MODEL` = `openrouter/free`
   - `INGEST_TOKEN` = a long random secret
   - `DATABASE_PATH` = `/var/data/property_assistant.db` (if using a persistent disk) or `/tmp/property_assistant.db` for ephemeral free service
5. Choose the Free plan if available. Set health check path to `/health`.
6. Deploy. Your app will receive a URL like `https://<service-name>.onrender.com`.
7. Trigger ingestion:
```bash
curl -X POST https://YOUR-APP.onrender.com/api/ingest \\
  -H "X-Ingest-Token: YOUR_INGEST_TOKEN"
```
8. Verify `https://YOUR-APP.onrender.com/health`, `/api/sources`, and the chat UI.

### Free-plan caveats
Render free web services spin down after 15 minutes of inactivity and take time to wake up. Their filesystem is ephemeral unless persistent storage is configured; the database can be lost on restart/redeploy. The app does not promise always-on availability on the free tier.

## API
- `GET /` — chatbot UI
- `GET /health` — health and indexed document count
- `GET /api/sources` — indexed page inventory
- `POST /api/chat` — `{"message":"What is Wasalt?"}`
- `POST /api/ingest` — protected crawl; header `X-Ingest-Token`

## Tests
```bash
python -m unittest discover -s tests -v
```
