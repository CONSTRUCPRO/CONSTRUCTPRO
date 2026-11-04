import os

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

app = FastAPI(title="CONSTRUCTPRO")


@app.get("/")
def root():
    return {"message": "CONSTRUCTPRO funcionando"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "environment": os.getenv("APP_ENV", "development"),
    }