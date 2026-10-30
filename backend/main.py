
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

@app.get("/buoys", response_model=list[MeasurementOut])
def get_buoys(db: Session = Depends(get_db)):

    measurements = db.scalars(
        select(Measurement).order_by(
            Measurement.measured_at.desc(),
            Measurement.received_at.desc(),
        )
    ).all()

    latest = {}

    for measurement in measurements:
        latest.setdefault(measurement.buoy_id, measurement)

    return list(latest.values())


# --------------------------------------------------
# 10. Retrieve measurement history
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
# 11. Run the server
# --------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=API_HOST, port=API_PORT)
