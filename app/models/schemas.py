from typing import List, Literal, Optional

from pydantic import BaseModel, Field


AttackType = Literal["packet_drop", "delay", "bandwidth_flood"]
TargetLink = Literal["Hop1", "Hop2"]


class AttackProfile(BaseModel):
    attack_type: AttackType
    attack_probability: float = Field(default=0.15, ge=0.0, le=1.0)
    attack_duration: int = Field(default=8, ge=1, le=1000)
    target_link: TargetLink = "Hop1"


class StartSimulationRequest(BaseModel):
    sensors: int = Field(default=5, ge=1, le=50)
    step_interval_sec: float = Field(default=0.5, ge=0.05, le=5.0)
    relay_buffer_size: int = Field(default=50, ge=1, le=10000)
    base_bandwidth_packets: int = Field(default=3, ge=1, le=200)
    attack_profiles: Optional[List[AttackProfile]] = None


class BasicResponse(BaseModel):
    status: str
    message: str
