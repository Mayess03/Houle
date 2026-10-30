
import os
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from sqlalchemy import (
    create_engine,
    String,
    Float,
    DateTime,
    select,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
    Session,
)
from sqlalchemy.exc import IntegrityError


# --------------------------------------------------
# 1. Configuration
# --------------------------------------------------

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")

# Monitoring thresholds
LOW_BATTERY_THRESHOLD = float(
    os.getenv("LOW_BATTERY_THRESHOLD", "20")
)

HIGH_WAVE_THRESHOLD = float(
    os.getenv("HIGH_WAVE_THRESHOLD", "4.0")
)

BUOY_SILENCE_SECONDS = int(
    os.getenv("BUOY_SILENCE_SECONDS", "30")
)

# --------------------------------------------------
# 2. Database connection
# --------------------------------------------------

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


# --------------------------------------------------
# 3. Database model
# --------------------------------------------------

class Measurement(Base):
    __tablename__ = "measurements"

    measurement_id: Mapped[str] = mapped_column(
        String(150),
        primary_key=True,
    )

    buoy_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
    )

    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    wave_height: Mapped[float] = mapped_column(Float)
    battery_level: Mapped[float] = mapped_column(Float)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)


# --------------------------------------------------
# 4. API schemas
# --------------------------------------------------

class MeasurementIn(BaseModel):
    measurement_id: str = Field(min_length=1, max_length=150)
    buoy_id: str = Field(min_length=1, max_length=100)

    measured_at: datetime

    wave_height: float = Field(ge=0, le=30)
    battery_level: float = Field(ge=0, le=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    @field_validator("measured_at")
    @classmethod
    def require_timezone(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("measured_at must include a timezone")
        return value


class MeasurementOut(BaseModel):
    measurement_id: str
    buoy_id: str
    measured_at: datetime
    received_at: datetime
    wave_height: float
    battery_level: float
    latitude: float
    longitude: float

    model_config = {"from_attributes": True}

class BuoyStatusOut(BaseModel):
    buoy_id: str
    status: str
    last_seen_at: datetime
    latest_measurement: MeasurementOut
    alerts: list[str]


class AlertOut(BaseModel):
    buoy_id: str
    type: str
    severity: str
    message: str
    value: float
    threshold: float

class StatsOut(BaseModel):
    total_buoys: int
    online_buoys: int
    silent_buoys: int
    buoys_with_low_battery: int
    buoys_with_high_waves: int
    total_active_alerts: int

# --------------------------------------------------
# 5. Database dependency
# --------------------------------------------------

def get_db():
    with SessionLocal() as db:
        yield db


# --------------------------------------------------
# 6. Application lifecycle
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Houle API",
    description="Ocean buoy monitoring backend",
    version="1.0.0",
    lifespan=lifespan,
)


# --------------------------------------------------
# 7. Health endpoints
# --------------------------------------------------

@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.get("/readyz")
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )


# --------------------------------------------------
# 8. Receive measurements
# --------------------------------------------------

@app.post("/measurements")
def ingest_measurement(
    data: MeasurementIn,
    db: Session = Depends(get_db),
):
    measurement = Measurement(**data.model_dump())

    db.add(measurement)

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        existing = db.get(Measurement, data.measurement_id)

        if existing:
            return {
                "status": "duplicate_ignored",
                "measurement_id": data.measurement_id,
            }

        raise HTTPException(
            status_code=409,
            detail="Measurement could not be stored",
        )

    return {
        "status": "stored",
        "measurement_id": data.measurement_id,
    }


# --------------------------------------------------
# 9. Retrieve buoy states
# --------------------------------------------------

def get_fleet_data(db: Session):

    measurements = db.scalars(
        select(Measurement).order_by(
            Measurement.measured_at.desc(),
            Measurement.received_at.desc(),
        )
    ).all()

    latest_measurements = {}
    last_seen = {}

    for measurement in measurements:

        buoy_id = measurement.buoy_id

        # Latest measurement based on measured_at
        if buoy_id not in latest_measurements:
            latest_measurements[buoy_id] = measurement

        # Last communication based on received_at
        if (
            buoy_id not in last_seen
            or measurement.received_at > last_seen[buoy_id]
        ):
            last_seen[buoy_id] = measurement.received_at

    return latest_measurements, last_seen


def analyze_buoy(
    measurement: Measurement,
    last_seen: datetime,
    now: datetime,
):

    alerts = []

    # 1. Detect silent buoy
    silence_duration = (
        now - last_seen
    ).total_seconds()

    if silence_duration > BUOY_SILENCE_SECONDS:
        alerts.append("silent")

    # 2. Detect low battery
    if measurement.battery_level < LOW_BATTERY_THRESHOLD:
        alerts.append("low_battery")

    # 3. Detect high waves
    if measurement.wave_height > HIGH_WAVE_THRESHOLD:
        alerts.append("high_waves")

    return alerts


@app.get("/buoys", response_model=list[BuoyStatusOut])
def get_buoys(db: Session = Depends(get_db)):

    latest, last_seen = get_fleet_data(db)

    now = datetime.now(timezone.utc)

    results = []

    for buoy_id, measurement in latest.items():

        alerts = analyze_buoy(
            measurement,
            last_seen[buoy_id],
            now,
        )

        status = (
            "silent"
            if "silent" in alerts
            else "online"
        )

        results.append(
            BuoyStatusOut(
                buoy_id=buoy_id,
                status=status,
                last_seen_at=last_seen[buoy_id],
                latest_measurement=measurement,
                alerts=alerts,
            )
        )

    return results

# --------------------------------------------------
# 10. Active alerts
# --------------------------------------------------

@app.get("/alerts", response_model=list[AlertOut])
def get_alerts(db: Session = Depends(get_db)):

    latest, last_seen = get_fleet_data(db)

    now = datetime.now(timezone.utc)

    alerts = []

    for buoy_id, measurement in latest.items():

        detected = analyze_buoy(
            measurement,
            last_seen[buoy_id],
            now,
        )

        # Silent buoy
        if "silent" in detected:

            silence_duration = (
                now - last_seen[buoy_id]
            ).total_seconds()

            alerts.append(
                AlertOut(
                    buoy_id=buoy_id,
                    type="silent",
                    severity="critical",
                    message="Buoy stopped reporting measurements",
                    value=round(silence_duration, 2),
                    threshold=BUOY_SILENCE_SECONDS,
                )
            )

        # Low battery
        if "low_battery" in detected:

            alerts.append(
                AlertOut(
                    buoy_id=buoy_id,
                    type="low_battery",
                    severity="warning",
                    message="Buoy battery level is too low",
                    value=measurement.battery_level,
                    threshold=LOW_BATTERY_THRESHOLD,
                )
            )

        # High waves
        if "high_waves" in detected:

            alerts.append(
                AlertOut(
                    buoy_id=buoy_id,
                    type="high_waves",
                    severity="warning",
                    message="Wave height exceeds the configured threshold",
                    value=measurement.wave_height,
                    threshold=HIGH_WAVE_THRESHOLD,
                )
            )

    return alerts


# --------------------------------------------------
# 11. Fleet statistics
# --------------------------------------------------

@app.get("/stats", response_model=StatsOut)
def get_stats(db: Session = Depends(get_db)):

    latest, last_seen = get_fleet_data(db)

    now = datetime.now(timezone.utc)

    total_buoys = len(latest)

    online_buoys = 0
    silent_buoys = 0
    low_battery_buoys = 0
    high_waves_buoys = 0
    total_active_alerts = 0

    for buoy_id, measurement in latest.items():

        alerts = analyze_buoy(
            measurement,
            last_seen[buoy_id],
            now,
        )

        if "silent" in alerts:
            silent_buoys += 1
        else:
            online_buoys += 1

        if "low_battery" in alerts:
            low_battery_buoys += 1

        if "high_waves" in alerts:
            high_waves_buoys += 1

        total_active_alerts += len(alerts)

    return StatsOut(
        total_buoys=total_buoys,
        online_buoys=online_buoys,
        silent_buoys=silent_buoys,
        buoys_with_low_battery=low_battery_buoys,
        buoys_with_high_waves=high_waves_buoys,
        total_active_alerts=total_active_alerts,
    )


# --------------------------------------------------
# 12. Retrieve measurement history
# --------------------------------------------------

@app.get(
    "/buoys/{buoy_id}/history",
    response_model=list[MeasurementOut],
)
def get_history(
    buoy_id: str,
    limit: int = 100,
    db: Session = Depends(get_db),
):

    if not 1 <= limit <= 1000:
        raise HTTPException(
            status_code=422,
            detail="limit must be between 1 and 1000",
        )

    return db.scalars(
        select(Measurement)
        .where(Measurement.buoy_id == buoy_id)
        .order_by(Measurement.measured_at.desc())
        .limit(limit)
    ).all()


# --------------------------------------------------
# 13. Run the server
# --------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=API_HOST, port=API_PORT)
