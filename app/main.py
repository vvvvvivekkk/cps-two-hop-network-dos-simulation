from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import bind_engine, router
from app.core.database import DatabaseManager
from app.simulation.engine import SimulationEngine


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = str(BASE_DIR / "simulation.db")
STATIC_DIR = BASE_DIR / "app" / "static"

app = FastAPI(
    title="Transmission Scheduling for Remote State Estimation",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

db = DatabaseManager(DB_PATH)
engine = SimulationEngine(db)
bind_engine(engine)
app.include_router(router)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))
