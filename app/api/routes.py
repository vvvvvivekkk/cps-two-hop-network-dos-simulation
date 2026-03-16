from fastapi import APIRouter, HTTPException

from app.models.schemas import BasicResponse, StartSimulationRequest
from app.simulation.engine import SimulationEngine


router = APIRouter()
_engine: SimulationEngine | None = None


def bind_engine(engine: SimulationEngine) -> None:
    global _engine
    _engine = engine


def get_engine() -> SimulationEngine:
    if _engine is None:
        raise HTTPException(status_code=500, detail="Simulation engine is not initialized")
    return _engine


@router.post("/start_simulation", response_model=BasicResponse)
def start_simulation(payload: StartSimulationRequest) -> BasicResponse:
    result = get_engine().start(payload)
    return BasicResponse(status=result["status"], message=result["message"])


@router.post("/stop_simulation", response_model=BasicResponse)
def stop_simulation() -> BasicResponse:
    result = get_engine().stop()
    return BasicResponse(status=result["status"], message=result["message"])


@router.get("/network_status")
def network_status() -> dict:
    return get_engine().network_status()


@router.get("/attack_status")
def attack_status() -> dict:
    return get_engine().attack_status()


@router.get("/estimation_data")
def estimation_data(limit: int = 250) -> dict:
    return get_engine().estimation_data(limit=limit)


@router.get("/network_metrics")
def network_metrics(limit: int = 250) -> dict:
    return get_engine().network_metrics(limit=limit)


@router.get("/logs")
def logs(limit: int = 250) -> dict:
    return get_engine().logs(limit=limit)
