FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# sentence-transformers is required in production (not just eval/local dev):
# core/embeddings.py's get_embedder()/get_reranker() back both the primary
# Gemini RAG retrieval path and its fallback chain, so without it itinerary
# generation fails end-to-end. The rest of requirements-ml.txt (langchain,
# groq/openai/anthropic eval clients) is genuinely eval-only — confirmed no
# production code under chains/, routers/, services/, core/ imports them —
# so only this one package is installed here, not the full heavy file.
RUN pip install --no-cache-dir sentence-transformers==3.0.0

# scrapers/district_events.py needs a real headless Chromium to render
# District.in's client-side SPA (no public API/RSS exists for it — see that
# module's docstring). `--with-deps` additionally installs Chromium's
# system library dependencies (fonts, X11/GTK libs, etc.) that `python:3.11-
# slim` doesn't ship with; this noticeably increases image size/build time,
# but only this one scraper needs it (everything else in scrapers/ is a
# plain httpx GET).
RUN playwright install --with-deps chromium

COPY . .

# Railway injects $PORT; default to 8000 for local docker usage
ENV PORT=8000

EXPOSE $PORT

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:$PORT/health || exit 1

CMD uvicorn main:app --host 0.0.0.0 --port $PORT
