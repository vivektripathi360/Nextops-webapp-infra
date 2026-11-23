import json
from datetime import datetime, timedelta
import asyncpg
from config import settings

pool: asyncpg.Pool | None = None

DEVICE_METADATA = {
    "COAL-FEEDER-01": {"name": "Coal Conveyor & Feeder", "category": "Fuel Ingestion System"},
    "FURNACE-01": {"name": "Boiler Combustion Furnace", "category": "Thermal Combustion Island"},
    "BOILER-01": {"name": "Superheated Steam Boiler", "category": "Vapor Generation Core"},
    "CHIMNEY-01": {"name": "Flue Scrubber & Chimney", "category": "Environmental Scrubbing & Exhaust"},
    "STEAM-LINE-01": {"name": "Main Steam Header Pipe", "category": "High-Pressure Steam Conduit"},
    "TURBINE-01": {"name": "Multi-Stage Steam Turbine", "category": "Kinetic Expansion Core"},
    "GENERATOR-01": {"name": "Electric Power Generator", "category": "Electromagnetic Generation"},
    "TRANSFORMER-01": {"name": "Step-Up Grid Transformer", "category": "Substation Voltage Step-Up"},
    "CONDENSER-01": {"name": "Surface Steam Condenser", "category": "Phase Transition & Vacuum Island"},
    "FEEDWATER-01": {"name": "Boiler Feedwater Return", "category": "Closed-Loop Feedwater Circuit"},
    "COOLING-WATER-01": {"name": "River Cooling Water Intake", "category": "Heat Rejection & Environmental Cycle"},
    "TRANSMISSION-01": {"name": "400 kV Transmission Lines", "category": "High-Voltage Power Dispatch"}
}

async def connect_db():
    global pool
    pool = await asyncpg.create_pool(
        dsn=settings.DATABASE_URL,
        min_size=2,
        max_size=10,
    )

async def disconnect_db():
    global pool
    if pool:
        await pool.close()
        pool = None

def calculate_health(temperature: float, pressure: float, flow_rate: float, device_type: str = ""):
    t = temperature or 0.0
    p = pressure or 0.0
    f = flow_rate or 0.0
    
    score = 100.0
    dtype = (device_type or "").upper()
    
    if "COAL" in dtype:
        if t > 65.0: # motor bearing temp
            score -= (t - 65.0) * 1.5
        if f < 180.0 and f > 0:
            score -= (180.0 - f) * 0.3
    elif "FURNACE" in dtype:
        if t > 1250.0:
            score -= (t - 1250.0) * 0.8
        elif t < 1050.0 and t > 0:
            score -= (1050.0 - t) * 0.5
        if p > 1.2:
            score -= (p - 1.2) * 80.0
    elif "BOILER" in dtype:
        if t > 565.0:
            score -= (t - 565.0) * 1.5
        if p > 185.0:
            score -= (p - 185.0) * 1.5
        if f < 1600.0 and f > 0:
            score -= (1600.0 - f) * 0.1
    elif "CHIMNEY" in dtype:
        if t > 150.0:
            score -= (t - 150.0) * 1.2
        if f > 200.0: # NOx high
            score -= (f - 200.0) * 0.5
    elif "STEAM" in dtype:
        if t > 560.0:
            score -= (t - 560.0) * 1.5
        if p > 185.0:
            score -= (p - 185.0) * 1.5
    elif "TURBINE" in dtype:
        if t > 140.0:
            score -= (t - 140.0) * 1.2
        if p > 25.0:
            score -= (p - 25.0) * 2.0
    elif "GENERATOR" in dtype:
        if t > 80.0:
            score -= (t - 80.0) * 1.5
        if f < 500.0 and f > 0:
            score -= (500.0 - f) * 0.1
    elif "TRANSFORMER" in dtype:
        if t > 85.0:
            score -= (t - 85.0) * 1.5
        if p > 420.0:
            score -= (p - 420.0) * 2.0
    elif "CONDENSER" in dtype:
        if t > 45.0:
            score -= (t - 45.0) * 2.0
        if p > 0.1: # Vacuum lost
            score -= (p - 0.1) * 300.0
    elif "FEEDWATER" in dtype:
        if p < 170.0 and p > 0:
            score -= (170.0 - p) * 1.5
        if t > 300.0:
            score -= (t - 300.0) * 1.5
    elif "COOLING" in dtype or "HEAT_EXCHANGER" in dtype:
        if t > 32.0:
            score -= (t - 32.0) * 3.0
        if p > 8.0:
            score -= (p - 8.0) * 4.0
    elif "TRANSMISSION" in dtype:
        if p > 420.0:
            score -= (p - 420.0) * 2.0
    else:
        if t > 550.0:
            score -= (t - 550.0) * 0.5
        if p > 150.0:
            score -= (p - 150.0) * 0.5

    score = max(10, min(100, int(score)))
    
    if score <= 50:
        return "critical", score
    elif score <= 80:
        return "warning", score
    else:
        return "NORMAL", score

async def fetch_summary():
    query = """
        WITH LatestReadings AS (
            SELECT DISTINCT ON (device_id)
                device_id,
                device_type,
                temperature,
                pressure,
                flow_rate,
                timestamp
            FROM telemetry
            ORDER BY device_id, timestamp DESC
        )
        SELECT 
            COUNT(DISTINCT device_id) as online_assets,
            MAX(timestamp) as last_update,
            AVG(temperature) as avg_temp,
            AVG(pressure) as avg_press
        FROM LatestReadings;
    """
    row = await pool.fetchrow(query)

    boiler_row = await pool.fetchrow("""
        SELECT temperature, pressure FROM telemetry
        WHERE device_type = 'BOILER'
        ORDER BY timestamp DESC LIMIT 1;
    """)

    gen_row = await pool.fetchrow("""
        SELECT flow_rate FROM telemetry
        WHERE device_type = 'GENERATOR'
        ORDER BY timestamp DESC LIMIT 1;
    """)

    net_gen = gen_row["flow_rate"] if gen_row and gen_row["flow_rate"] else 660.0
    boiler_temp = boiler_row["temperature"] if boiler_row and boiler_row["temperature"] else 542.0
    boiler_press = boiler_row["pressure"] if boiler_row and boiler_row["pressure"] else 175.4

    return {
        "onlineAssets": row["online_assets"] or 12,
        "totalAssets": 12,
        "lastUpdate": row["last_update"],
        "netGenerationMw": round(float(net_gen), 1),
        "steamTemperatureC": round(float(boiler_temp), 1),
        "steamPressureBar": round(float(boiler_press), 1),
        "plantCycleEfficiency": 39.8,
        "systemFrequencyHz": 50.00
    }

async def fetch_regions_summary():
    query = """
        WITH LatestDevices AS (
            SELECT DISTINCT ON (device_id)
                device_id,
                device_type,
                refinery_region,
                temperature,
                pressure,
                flow_rate,
                timestamp as last_seen
            FROM telemetry
            ORDER BY device_id, timestamp DESC
        )
        SELECT refinery_region, device_type, temperature, pressure, flow_rate, last_seen
        FROM LatestDevices;
    """
    rows = await pool.fetch(query)
    
    regions = {}
    now = datetime.utcnow()
    for r in rows:
        region = r["refinery_region"] or "STATION_1"
        if region not in regions:
            regions[region] = {"total_devices": 0, "online_devices": 0, "alert_devices": 0}
            
        regions[region]["total_devices"] += 1
        status, _ = calculate_health(r["temperature"], r["pressure"], r["flow_rate"], r["device_type"])
        
        is_online = True
        if r["last_seen"]:
            time_diff = (now - r["last_seen"].replace(tzinfo=None)).total_seconds()
            if time_diff > 300:
                is_online = False
                
        if is_online:
            regions[region]["online_devices"] += 1
            
        if status in ["warning", "critical"]:
            regions[region]["alert_devices"] += 1
            
    return [
        {
            "region": k,
            "total_devices": v["total_devices"],
            "online_devices": v["online_devices"],
            "alert_devices": v["alert_devices"],
            "online": v["online_devices"],
            "alerts": v["alert_devices"]
        }
        for k, v in regions.items()
    ]

async def fetch_devices():
    query = """
        SELECT DISTINCT ON (device_id)
            device_id,
            device_type,
            refinery_region,
            timestamp as last_seen,
            temperature,
            pressure,
            flow_rate,
            COALESCE(component_metrics, '{}'::jsonb) as component_metrics
        FROM telemetry
        ORDER BY device_id, timestamp DESC;
    """
    rows = await pool.fetch(query)
    
    devices = []
    for r in rows:
        d = dict(r)
        if "component_metrics" in d and isinstance(d["component_metrics"], str):
            try:
                d["component_metrics"] = json.loads(d["component_metrics"])
            except Exception:
                d["component_metrics"] = {}

        meta = DEVICE_METADATA.get(d["device_id"], {})
        d["name"] = meta.get("name", d["device_id"])
        d["category"] = meta.get("category", d["device_type"])

        status, health_score = calculate_health(
            d.get("temperature"),
            d.get("pressure"),
            d.get("flow_rate"),
            d.get("device_type")
        )
        d["status"] = status
        d["health_score"] = health_score
        d["operating_hours"] = 8420
        d["last_inspection"] = "2026-08-15"
        devices.append(d)
        
    return devices

async def fetch_top_anomalous_devices():
    devices = await fetch_devices()
    anomalous = [d for d in devices if d["status"] in ["warning", "critical"]]
    anomalous.sort(key=lambda x: x["health_score"])
    return anomalous[:5]

async def fetch_latest_telemetry(device_id: str = None):
    if device_id:
        query = """
            SELECT * FROM telemetry
            WHERE device_id = $1
            ORDER BY timestamp DESC
            LIMIT 1;
        """
        row = await pool.fetchrow(query, device_id)
        if row:
            d = dict(row)
            if "component_metrics" in d and isinstance(d["component_metrics"], str):
                try:
                    d["component_metrics"] = json.loads(d["component_metrics"])
                except Exception:
                    d["component_metrics"] = {}
            status, health_score = calculate_health(
                d.get("temperature"),
                d.get("pressure"),
                d.get("flow_rate"),
                d.get("device_type")
            )
            d["status"] = status
            d["health_score"] = health_score
            meta = DEVICE_METADATA.get(device_id, {})
            d["name"] = meta.get("name", device_id)
            d["category"] = meta.get("category", d["device_type"])
            return d
        return None
    return None

async def fetch_device_trends(device_id: str, hours: int = 1):
    query = """
        SELECT timestamp, temperature, pressure, flow_rate,
               COALESCE(component_metrics, '{}'::jsonb) as component_metrics
        FROM telemetry
        WHERE device_id = $1
          AND timestamp >= NOW() - INTERVAL '1 hour' * $2
        ORDER BY timestamp ASC;
    """
    rows = await pool.fetch(query, device_id, hours)
    results = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("component_metrics"), str):
            try:
                d["component_metrics"] = json.loads(d["component_metrics"])
            except Exception:
                d["component_metrics"] = {}
        results.append(d)
    return results

async def fetch_throughput():
    query = """
        SELECT
            date_trunc('minute', timestamp) as minute,
            count(*)
        FROM telemetry
        GROUP BY minute
        ORDER BY minute DESC
        LIMIT 60;
    """
    rows = await pool.fetch(query)
    
    data = [dict(r) for r in rows]
    data.reverse()
    
    formatted = []
    for r in data:
        formatted.append({
            "minute": r["minute"].strftime("%H:%M") if r["minute"] else "",
            "count": r["count"]
        })
    return formatted

async def fetch_alarms():
    """
    Fetch alarms from alarms table or evaluate active alarms against safety limits.
    """
    try:
        alarms_rows = await pool.fetch("""
            SELECT id, alarm_code, device_id, device_type, severity, metric_name,
                   current_value, threshold_value, message, status, created_at
            FROM alarms
            WHERE status = 'ACTIVE'
            ORDER BY created_at DESC
            LIMIT 20;
        """)
        if alarms_rows:
            return [dict(r) for r in alarms_rows]
    except Exception:
        pass

    # If table is empty or being initialized, generate dynamic alarm evaluations from live telemetry
    devices = await fetch_devices()
    alarms = []
    idx = 1
    for d in devices:
        t = d.get("temperature", 0)
        p = d.get("pressure", 0)
        f = d.get("flow_rate", 0)
        cid = d.get("device_id")
        dtype = d.get("device_type", "")
        
        if cid == "BOILER-01" and t > 565.0:
            alarms.append({
                "id": f"ALM-10{idx:02d}",
                "timestamp": d.get("last_seen", datetime.utcnow()).isoformat(),
                "severity": "CRITICAL",
                "assetId": cid,
                "assetType": dtype,
                "unit": "UNIT_1_SUPERCRITICAL",
                "metric": "Main Steam Temp",
                "currentValue": f"{t:.1f} °C",
                "threshold": "> 565.0 °C",
                "message": "Superheater outlet steam temperature high",
                "status": "ACTIVE"
            })
            idx += 1
        elif cid == "FURNACE-01" and p > 1.2:
            alarms.append({
                "id": f"ALM-10{idx:02d}",
                "timestamp": d.get("last_seen", datetime.utcnow()).isoformat(),
                "severity": "CRITICAL",
                "assetId": cid,
                "assetType": dtype,
                "unit": "UNIT_1_SUPERCRITICAL",
                "metric": "Furnace Draft",
                "currentValue": f"{p:.2f} bar",
                "threshold": "> 1.1 bar",
                "message": "Positive furnace pressure detected",
                "status": "ACTIVE"
            })
            idx += 1
        elif cid == "TURBINE-01" and t > 130.0:
            alarms.append({
                "id": f"ALM-10{idx:02d}",
                "timestamp": d.get("last_seen", datetime.utcnow()).isoformat(),
                "severity": "WARNING",
                "assetId": cid,
                "assetType": dtype,
                "unit": "UNIT_1_SUPERCRITICAL",
                "metric": "Turbine Exhaust Temp",
                "currentValue": f"{t:.1f} °C",
                "threshold": "> 130.0 °C",
                "message": "Exhaust hood temperature elevated",
                "status": "ACTIVE"
            })
            idx += 1

    return alarms
