"""
FastAPI app instance, route registration, startup (opens/initializes DB).
(DESIGN.md Section 8.)
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import db, games_api, leaderboard_api, pages, profiles_api

APP_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Tic Tac Toe Online")

app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

app.include_router(profiles_api.router)
app.include_router(games_api.router)
app.include_router(leaderboard_api.router)
app.include_router(pages.router)


@app.on_event("startup")
def on_startup():
    db.get_conn()  # opens the connection and runs schema init (db.py)
