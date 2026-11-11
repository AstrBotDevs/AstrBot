from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    admin_wallets,
    auth,
    billing,
    bot,
    orders,
    profile,
    tickets,
    usage,
    wallet,
)
from app.core.config import settings
from app.db.engine import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Fish API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(billing.router, prefix="/api/v1")
app.include_router(wallet.router, prefix="/api/v1")
app.include_router(orders.router, prefix="/api/v1")
app.include_router(bot.router, prefix="/api/v1")
app.include_router(usage.router, prefix="/api/v1")
app.include_router(profile.router, prefix="/api/v1")
app.include_router(tickets.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(admin_wallets.router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
