
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from config import settings

# Ingestion database functions
from ingestion_database import (
    connect_db as connect_ingestion_db,
    disconnect_db as disconnect_ingestion_db,
    insert_telemetry,
    insert_telemetry_batch,
    fetch_telemetry,
)

# Query database functions
from query_database import (
    connect_db as connect_query_db,
    disconnect_db as disconnect_query_db,
    fetch_summary,
    fetch_devices,
    fetch_latest_telemetry,
    fetch_device_trends,
    fetch_throughput,
    fetch_top_anomalous_devices,
    fetch_regions_summary,
    fetch_alarms,
)

from models import (
    TelemetryPayload,
    TelemetryRecord,
    TelemetryResponse,
    BatchTelemetryPayload,
    BatchTelemetryResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nextops-backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Connecting to PostgreSQL...")
    await connect_ingestion_db()
    try:
        await connect_query_db()
        logger.info("Both database pools connected")
        yield
    finally:
        await disconnect_query_db()
        await disconnect_ingestion_db()
        logger.info("Database connections closed")


app = FastAPI(
    title="NextOps Industrial Backend",
    description="Combined Ingestion and Query API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health APIs

@app.get("/")
@app.get("/api/v1")
async def root():
    return {
        "status": "OK",
        "message": "NextOps Backend is running"
    }


@app.get("/health")
@app.get("/api/v1/health")
async def health():
    return {"status": "UP"}


# Ingestion APIs

@app.get(
    "/api/v1/telemetry",
    response_model=list[TelemetryRecord],
)
async def get_telemetry(
    deviceId: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    try:
        rows = await fetch_telemetry(device_id=deviceId, limit=limit)

        return [
            TelemetryRecord(
                id=str(row["id"]),
                device_id=row["device_id"],
                device_type=row["device_type"],
                refinery_region=row["refinery_region"],
                timestamp=row["timestamp"],
                temperature=row["temperature"],
                pressure=row["pressure"],
                flow_rate=row["flow_rate"],
                component_metrics=row.get("component_metrics") or {},
                created_at=row["created_at"],
            )
            for row in rows
        ]
    except Exception as exc:
        logger.exception("Telemetry fetch failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post(
    "/api/v1/telemetry/ingest",
    response_model=TelemetryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_telemetry(payload: TelemetryPayload):
    try:
        record_id = await insert_telemetry(
            device_id=payload.deviceId,
            device_type=payload.deviceType,
            refinery_region=payload.refineryRegion,
            timestamp=payload.timestamp,
            temperature=payload.metrics.temperature,
            pressure=payload.metrics.pressure,
            flow_rate=payload.metrics.flow_rate,
            component_metrics=payload.componentMetrics,
        )

        return TelemetryResponse(
            status="accepted",
            id=record_id,
            message="Telemetry data ingested successfully",
        )
    except Exception as exc:
        logger.exception("Telemetry ingestion failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post(
    "/api/v1/telemetry/batch",
    response_model=BatchTelemetryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_batch_telemetry(payload: BatchTelemetryPayload):
    try:
        readings = [
            {
                "device_id": item.deviceId,
                "device_type": item.deviceType,
                "refinery_region": item.refineryRegion,
                "timestamp": item.timestamp,
                "temperature": item.metrics.temperature,
                "pressure": item.metrics.pressure,
                "flow_rate": item.metrics.flow_rate,
                "component_metrics": item.componentMetrics,
            }
            for item in payload.readings
        ]

        ids = await insert_telemetry_batch(readings)

        return BatchTelemetryResponse(
            status="accepted",
            ingested_count=len(ids),
            ids=ids,
            message="Batch telemetry data ingested successfully",
        )
    except Exception as exc:
        logger.exception("Batch ingestion failed")
        raise HTTPException(status_code=500, detail=str(exc))


# Query APIs

@app.get("/dashboard/summary")
@app.get("/api/v1/dashboard/summary")
async def get_summary():
    try:
        return await fetch_summary()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/devices")
@app.get("/api/v1/devices")
async def get_devices():
    try:
        return await fetch_devices()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/devices/{device_id}/latest")
@app.get("/api/v1/devices/{device_id}/latest")
async def get_latest_device_data(device_id: str):
    try:
        data = await fetch_latest_telemetry(device_id)
        if not data:
            raise HTTPException(status_code=404, detail="No telemetry found")
        return data
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/devices/{device_id}/trends")
@app.get("/api/v1/devices/{device_id}/trends")
async def get_device_trends(
    device_id: str,
    hours: int = Query(1),
):
    try:
        return await fetch_device_trends(device_id, hours)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/devices/top-anomalous")
@app.get("/api/v1/devices/top-anomalous")
async def get_top_anomalous():
    try:
        return await fetch_top_anomalous_devices()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/dashboard/throughput")
@app.get("/api/v1/dashboard/throughput")
async def get_throughput():
    try:
        return await fetch_throughput()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/dashboard/regions")
@app.get("/api/v1/dashboard/regions")
async def get_regions():
    try:
        return await fetch_regions_summary()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/alarms")
@app.get("/api/v1/alarms")
async def get_alarms():
    try:
        return await fetch_alarms()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
