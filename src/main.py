from fastapi import FastAPI

from src.api.routes import webhook

app = FastAPI(title="Event Ingestion API")

app.include_router(webhook.router)


@app.get("/health")
def health():
    return {"status": "ok"}