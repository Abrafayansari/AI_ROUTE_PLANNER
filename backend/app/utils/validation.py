from __future__ import annotations

import re
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

TIME_24H_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

TravelModeLiteral = Literal[
    "simulated_vehicle",
    "simulated_walking",
    "simulated_van",
    "DRIVE",
    "TWO_WHEELER",
    "WALK",
]
OptimizationObjectiveLiteral = Literal["FASTEST_TIME", "SHORTEST_DISTANCE"]


def parse_time_to_minutes(time_str: str) -> int:
    m = TIME_24H_RE.match(time_str)
    if not m:
        return -1
    return int(m.group(1)) * 60 + int(m.group(2))


def is_valid_uuid(value: str) -> bool:
    try:
        UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False


def _validate_uuid_list(ids: list[str], allow_empty: bool = False) -> list[str]:
    if not allow_empty and len(ids) < 1:
        raise ValueError("Select at least 1 distributor")
    seen: set[str] = set()
    for item in ids:
        if not is_valid_uuid(item):
            raise ValueError(f"Invalid UUID: {item}")
        norm = str(UUID(item))
        if norm in seen:
            raise ValueError("Duplicate distributor IDs are not allowed")
        seen.add(norm)
    return [str(UUID(item)) for item in ids]


class OfficeInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=2, max_length=120)
    address: str = Field(..., min_length=3, max_length=250)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    is_default: bool = True

    @field_validator("name", "address", mode="before")
    @classmethod
    def strip_text(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v


class DistributorInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=2, max_length=140)
    contact_person: str = Field(..., min_length=2, max_length=120)
    phone: str = Field(..., min_length=7, max_length=25)
    email: Optional[EmailStr | Literal[""]] = ""
    address: str = Field(..., min_length=3, max_length=250)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    priority: int = Field(..., ge=1, le=5)
    visit_duration_minutes: int = Field(..., ge=5, le=480)
    opening_time: str
    closing_time: str
    is_active: bool = True
    notes: str = Field(default="", max_length=1000)

    @field_validator("name", "contact_person", "phone", "address", "email", mode="before")
    @classmethod
    def strip_strings(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("opening_time")
    @classmethod
    def check_open(cls, v: str) -> str:
        if not TIME_24H_RE.match(v):
            raise ValueError("Opening time must be HH:MM (24h)")
        return v

    @field_validator("closing_time")
    @classmethod
    def check_close(cls, v: str) -> str:
        if not TIME_24H_RE.match(v):
            raise ValueError("Closing time must be HH:MM (24h)")
        return v

    @model_validator(mode="after")
    def validate_hours(self):
        if parse_time_to_minutes(self.closing_time) <= parse_time_to_minutes(self.opening_time):
            raise ValueError("Closing time must be strictly after opening time")
        return self


class ClusterRunInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    distributorIds: list[str]
    k: int = Field(..., ge=1)
    seed: int = Field(default=42, ge=0, le=1_000_000)
    maxIterations: int = Field(default=100, ge=1, le=500)
    initMethod: Literal["kmeans++", "random"] = "kmeans++"
    routePlanId: Optional[str] = None

    @field_validator("distributorIds")
    @classmethod
    def check_ids(cls, v: list[str]) -> list[str]:
        return _validate_uuid_list(v)

    @field_validator("routePlanId")
    @classmethod
    def check_plan_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not is_valid_uuid(v):
            raise ValueError("Invalid routePlanId UUID")
        return str(UUID(v))


class ScheduleRunInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    distributorIds: list[str]
    scheduleDate: str
    workStartTime: str
    workEndTime: str
    slotIncrementMinutes: int = Field(default=15, ge=5, le=60)
    travelBufferMinutes: int = Field(default=15, ge=0, le=120)
    lunchBreakEnabled: bool = True
    lunchStartTime: str = "12:30"
    lunchDurationMinutes: int = Field(default=60, ge=15, le=120)
    maxVisitsPerDay: int = Field(default=10, ge=1, le=30)
    travelMode: TravelModeLiteral = "DRIVE"
    optimizationObjective: OptimizationObjectiveLiteral = "FASTEST_TIME"
    useRoadTravelTimes: bool = True
    officeId: Optional[str] = None
    routePlanId: Optional[str] = None

    @field_validator("distributorIds")
    @classmethod
    def check_ids(cls, v: list[str]) -> list[str]:
        return _validate_uuid_list(v)

    @field_validator("scheduleDate")
    @classmethod
    def check_date(cls, v: str) -> str:
        if not DATE_RE.match(v):
            raise ValueError("Schedule date must be YYYY-MM-DD")
        return v

    @field_validator("workStartTime", "workEndTime", "lunchStartTime")
    @classmethod
    def check_hhmm(cls, v: str) -> str:
        if not TIME_24H_RE.match(v):
            raise ValueError("Time values must be HH:MM (24h)")
        return v

    @field_validator("officeId", "routePlanId")
    @classmethod
    def check_optional_uuid(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not is_valid_uuid(v):
            raise ValueError("Invalid UUID")
        return str(UUID(v))

    @model_validator(mode="after")
    def validate_work_hours(self):
        if parse_time_to_minutes(self.workEndTime) <= parse_time_to_minutes(self.workStartTime):
            raise ValueError("Work end time must be after work start time")
        return self


class SmartFixInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: Literal["QUICK_FIX", "SMART_OPTIMIZE", "SUGGESTIONS_ONLY"] = "QUICK_FIX"
    routePlanId: Optional[str] = None
    officeId: Optional[str] = None
    distributorIds: Optional[list[str]] = None
    scheduleDate: Optional[str] = "2026-11-21"
    workStartTime: str = "09:00"
    workEndTime: str = "17:00"
    slotIncrementMinutes: int = Field(default=15, ge=5, le=60)
    travelBufferMinutes: int = Field(default=15, ge=0, le=120)
    lunchBreakEnabled: bool = True
    lunchStartTime: str = "12:30"
    lunchDurationMinutes: int = Field(default=60, ge=15, le=120)
    maxVisitsPerDay: int = Field(default=10, ge=1, le=30)
    travelMode: TravelModeLiteral = "DRIVE"
    optimizationObjective: OptimizationObjectiveLiteral = "FASTEST_TIME"
    useRoadTravelTimes: bool = True

    @field_validator("routePlanId", "officeId")
    @classmethod
    def check_smart_fix_uuid(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not is_valid_uuid(v):
            raise ValueError("Invalid UUID")
        return str(UUID(v))

    @field_validator("distributorIds")
    @classmethod
    def check_dist_ids(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return None
        return _validate_uuid_list(v, allow_empty=True)

    @field_validator("workStartTime", "workEndTime", "lunchStartTime")
    @classmethod
    def check_smart_fix_hhmm(cls, v: str) -> str:
        if not TIME_24H_RE.match(v):
            raise ValueError("Time values must be HH:MM (24h)")
        return v


class ApplySmartFixInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    routePlanId: Optional[str] = None
    officeId: Optional[str] = None
    scheduleDate: Optional[str] = "2026-11-21"
    mode: str = "QUICK_FIX"
    scheduled: list[dict[str, Any]] = Field(..., min_length=1)

    @field_validator("routePlanId", "officeId")
    @classmethod
    def check_apply_uuid(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not is_valid_uuid(v):
            raise ValueError("Invalid UUID")
        return str(UUID(v))
        if parse_time_to_minutes(self.workEndTime) <= parse_time_to_minutes(self.workStartTime):
            raise ValueError("Work end time must be after work start time")
        return self


class GraphMatrixInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    officeId: str
    distributorIds: list[str] = Field(..., max_length=25)
    seed: int = Field(default=42, ge=0, le=1_000_000)
    distanceMultiplier: float = Field(default=1.0, ge=1.0, le=3.0)
    travelMode: TravelModeLiteral = "DRIVE"
    optimizationObjective: OptimizationObjectiveLiteral = "FASTEST_TIME"

    @field_validator("officeId")
    @classmethod
    def check_office_id(cls, v: str) -> str:
        if not is_valid_uuid(v):
            raise ValueError("Invalid office ID")
        return str(UUID(v))

    @field_validator("distributorIds")
    @classmethod
    def check_ids(cls, v: list[str]) -> list[str]:
        if len(v) > 25:
            raise ValueError("Maximum 25 distributors supported")
        return _validate_uuid_list(v)


class OptimizePreviewInput(GraphMatrixInput):
    returnToOffice: bool = True
    gaPopulationSize: int = Field(default=80, ge=20, le=300)
    gaGenerations: int = Field(default=150, ge=20, le=500)
    gaMutationRate: float = Field(default=0.18, ge=0.01, le=0.8)


class CreateRoutePlanInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=2, max_length=140)
    planDate: str
    officeId: str
    distributorIds: list[str] = Field(..., max_length=25)
    travelMode: TravelModeLiteral = "DRIVE"
    optimizationObjective: OptimizationObjectiveLiteral = "FASTEST_TIME"
    returnToOffice: bool = True
    distanceMultiplier: float = Field(default=1.0, ge=1.0, le=3.0)
    graphSeed: int = Field(default=42, ge=0, le=1_000_000)
    notes: str = Field(default="", max_length=1000)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("planDate")
    @classmethod
    def check_date(cls, v: str) -> str:
        if not DATE_RE.match(v):
            raise ValueError("Plan date must be YYYY-MM-DD")
        return v

    @field_validator("officeId")
    @classmethod
    def check_office(cls, v: str) -> str:
        if not is_valid_uuid(v):
            raise ValueError("Invalid office ID")
        return str(UUID(v))

    @field_validator("distributorIds")
    @classmethod
    def check_ids(cls, v: list[str]) -> list[str]:
        if len(v) > 25:
            raise ValueError("Maximum 25 distributors per route plan")
        return _validate_uuid_list(v)


class OptimizeRouteInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    distributorIds: Optional[list[str]] = None
    selectedAlgorithm: Optional[Literal["BFS", "UCS", "A*", "GENETIC_ALGORITHM"]] = None
    optimizationObjective: Optional[OptimizationObjectiveLiteral] = None
    gaPopulationSize: int = Field(default=80, ge=20, le=300)
    gaGenerations: int = Field(default=150, ge=20, le=500)
    gaMutationRate: float = Field(default=0.18, ge=0.01, le=0.8)
    seed: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    distanceMultiplier: Optional[float] = Field(default=None, ge=1.0, le=3.0)
    returnToOffice: Optional[bool] = None
    travelMode: Optional[TravelModeLiteral] = None

    @field_validator("distributorIds")
    @classmethod
    def check_ids(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return None
        if len(v) > 25:
            raise ValueError("Maximum 25 distributors per optimization")
        return _validate_uuid_list(v)


class UpdateRoutePlanInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = Field(default=None, min_length=2, max_length=140)
    planDate: Optional[str] = None
    status: Optional[Literal["draft", "optimized", "scheduled", "in_progress", "completed"]] = None
    selectedAlgorithm: Optional[Literal["BFS", "UCS", "A*", "GENETIC_ALGORITHM"]] = None
    optimizationObjective: Optional[OptimizationObjectiveLiteral] = None
    notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("planDate")
    @classmethod
    def check_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not DATE_RE.match(v):
            raise ValueError("Plan date must be YYYY-MM-DD")
        return v


class WaypointCoordInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)


class RouteGeometryInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    waypoints: list[WaypointCoordInput] = Field(..., min_length=2, max_length=27)
    travelMode: TravelModeLiteral = "DRIVE"
    optimizationObjective: OptimizationObjectiveLiteral = "FASTEST_TIME"


class StopStatusInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["pending", "visited", "skipped"]
    notes: Optional[str] = Field(default=None, max_length=500)


class VisitDelayInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    distributorId: Optional[str] = None
    distributorName: Optional[str] = None
    distanceKm: Optional[float] = Field(default=None, ge=0.0, le=2000.0)
    visitDurationMinutes: Optional[int] = Field(default=None, ge=1, le=1440)
    timeSlot: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    distanceCategory: Optional[Literal["Near", "Medium", "Far"]] = None
    visitDurationCategory: Optional[Literal["Short", "Medium", "Long"]] = None
    priorityCategory: Optional[Literal["Low", "Medium", "High"]] = None
    routePlanId: Optional[str] = None
    stopOrder: Optional[int] = Field(default=None, ge=1)
    allowPartial: bool = False
    saveToDb: bool = False

    @field_validator("distributorId", "routePlanId")
    @classmethod
    def check_optional_uuid(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not is_valid_uuid(v):
            raise ValueError(f"Invalid UUID format: {v}")
        return str(UUID(v))


class RouteDelayInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    routePlanId: str
    saveToDb: bool = True

    @field_validator("routePlanId")
    @classmethod
    def check_plan_uuid(cls, v: str) -> str:
        if not is_valid_uuid(v):
            raise ValueError("Invalid routePlanId UUID")
        return str(UUID(v))
