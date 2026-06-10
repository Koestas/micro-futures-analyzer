from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import asyncio
import os
import uvicorn

load_dotenv()

from database import init_db
from routes.market import router as market_router
from routes.flow import router as flow_router
from routes.tape import router as tape_router
from routes.replay import router as replay_router
from routes.journal import router as journal_router
from routes.providers import router as providers_router
from routes.schwab import router as schwab_router
from routes.ict import router as ict_router
from routes.risk import router as risk_router
from routes.learn import router as learn_router
from routes.backtest import router as backtest_router
from routes.projectx import router as projectx_router
from routes.autotrader import router as autotrader_router
from routes.botstats import router as botstats_router
from routes.scalp_backtest import router as scalp_bt_router


async def _background_refresh():
    """Proactively warm the Yahoo Finance + ProjectX data cache."""
    import providers.yahoo as yf
    from providers.calendar import get_calendar

    await asyncio.sleep(15)  # let server fully start first
    while True:
        try:
            yf.get_qqq_price()
            yf.get_futures_quotes()
            yf.get_news()
            yf.get_intraday("QQQ", "5m")
            get_calendar()
        except Exception:
            pass
        await asyncio.sleep(300)  # 5 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yahoo_task     = asyncio.create_task(_background_refresh())

    # ProjectX live data (non-blocking — logs warning if creds missing)
    import providers.projectx as px
    px_task = asyncio.create_task(px.background_task())

    # Auto-start the bot after ProjectX has time to authenticate
    import engines.auto_trader as at
    async def _delayed_bot_start():
        await asyncio.sleep(20)   # wait for ProjectX auth + contract cache
        await at.start()
        import logging
        logging.getLogger(__name__).info("Auto-trader started automatically")
    bot_task = asyncio.create_task(_delayed_bot_start())

    yield
    yahoo_task.cancel()
    px_task.cancel()
    bot_task.cancel()
    await at.stop()
    if px._ws_market:
        try:
            px._ws_market.stop()
        except Exception:
            pass


app = FastAPI(title="Micro Futures Analyzer", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market_router)
app.include_router(flow_router)
app.include_router(tape_router)
app.include_router(replay_router)
app.include_router(journal_router)
app.include_router(providers_router)
app.include_router(schwab_router)
app.include_router(ict_router)
app.include_router(risk_router)
app.include_router(learn_router)
app.include_router(backtest_router)
app.include_router(projectx_router)
app.include_router(autotrader_router)
app.include_router(botstats_router)
app.include_router(scalp_bt_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": str(exc), "path": str(request.url)})


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


# Serve the built React frontend — must come after all /api/* routes
_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST, "assets")), name="assets")

    @app.get("/{_full_path:path}")
    async def serve_spa(_full_path: str = ""):
        return FileResponse(os.path.join(_DIST, "index.html"))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
