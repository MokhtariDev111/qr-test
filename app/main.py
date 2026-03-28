from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from app.core import settings, init_db
from app.api import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print("✅ Database ready")
    yield


app = FastAPI(title="Smart University Toolbox", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/")
async def root():
    return {"message": "Smart University Toolbox API", "docs": "/docs"}
