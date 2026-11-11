"""A local service for inspecting voltage samples and sensor faults."""
from contextlib import closing
from datetime import datetime, timezone
import os
import sqlite3
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator


class Sample(BaseModel):
    device: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    sequence: int = Field(strict=True, ge=0, le=2**63 - 1)
    observed_at: datetime
    millivolts: int | None = Field(default=None, strict=True, ge=0, le=5000)

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(timezone.utc)


class Result(BaseModel):
    status: Literal["recorded", "duplicate"]
    state: Literal["normal", "above_limit", "sensor_fault"]


def create_app(db_path: str) -> FastAPI:
    api = FastAPI(title="Sensor Ops", version="1.0.0")

    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS samples (
            device TEXT NOT NULL, sequence INTEGER NOT NULL,
            observed_at TEXT NOT NULL, millivolts INTEGER, state TEXT NOT NULL,
            PRIMARY KEY (device, sequence))""")

    @api.post("/samples", response_model=Result)
    def record(sample: Sample):
        timestamp = sample.observed_at.isoformat(timespec="microseconds")
        mv = sample.millivolts
        state = "sensor_fault" if mv is None else "above_limit" if mv >= 2800 else "normal"
        with closing(sqlite3.connect(db_path, timeout=5)) as db, db:
            inserted = db.execute(
                "INSERT INTO samples VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                (sample.device, sample.sequence, timestamp, mv, state),
            )
            if inserted.rowcount == 1:
                return {"status": "recorded", "state": state}
            old = db.execute(
                "SELECT observed_at, millivolts, state FROM samples WHERE device=? AND sequence=?",
                (sample.device, sample.sequence),
            ).fetchone()
            if old[:2] != (timestamp, mv):
                raise HTTPException(409, "Sequence already used for different data")
            return {"status": "duplicate", "state": old[2]}

    @api.get("/devices/{device}/summary")
    def summarize(device: str):
        with closing(sqlite3.connect(db_path)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            rows = db.execute(
                "SELECT state, COUNT(*) AS count FROM samples WHERE device=? GROUP BY state",
                (device,),
            ).fetchall()
            counts = {"normal": 0, "above_limit": 0, "sensor_fault": 0}
            counts.update({row["state"]: row["count"] for row in rows})
            latest = db.execute(
                "SELECT sequence, observed_at, millivolts, state FROM samples WHERE device=? "
                "ORDER BY sequence DESC LIMIT 1",
                (device,),
            ).fetchone()
        if latest is None:
            raise HTTPException(404, "Device has no samples")
        return {"device": device, "counts": counts, "latest": dict(latest)}

    return api


def local_app() -> FastAPI:
    return create_app(os.environ.get("SENSOR_DB", "sensor.sqlite3"))
