"""ERP Adaptörü: OPC UA'dan veri okur, SQLite'ye yazar ve REST API sunar."""

from __future__ import annotations

import sqlite3
import time
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from plant import Plant
from opcua_server import run_opcua_server
from config import FACTORY_FURNACES, ERP_API_PORT, DB_PATH

app = FastAPI(title="ERP Simülasyon Adaptörü")

# ---------- Veritabanı (SQLite) ----------
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row
conn.executescript(
    """
    CREATE TABLE IF NOT EXISTS readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        furnace TEXT NOT NULL,
        temperature REAL NOT NULL,
        target_temperature REAL NOT NULL,
        status TEXT NOT NULL,
        burner_on INTEGER NOT NULL,
        gas_consumption REAL NOT NULL,
        energy_total REAL NOT NULL,
        cycle_time REAL NOT NULL,
        alarm TEXT,
        ts REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_readings_furnace_ts ON readings(furnace, ts);

    CREATE TABLE IF NOT EXISTS production_orders (
        id TEXT PRIMARY KEY,
        product TEXT NOT NULL,
        furnace TEXT NOT NULL,
        target_temp REAL NOT NULL,
        duration_min REAL NOT NULL,
        state TEXT NOT NULL,
        created_at REAL NOT NULL,
        started_at REAL,
        finished_at REAL,
        energy_total_m3 REAL,
        cycle_time_s REAL
    );
    """
)
conn.commit()


def add_reading(furnace, temperature, target_temperature, status, burner_on,
                gas_consumption, energy_total, cycle_time, alarm):
    conn.execute(
        """
        INSERT INTO readings
        (furnace, temperature, target_temperature, status, burner_on,
         gas_consumption, energy_total, cycle_time, alarm, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (furnace, temperature, target_temperature, status, int(burner_on),
         gas_consumption, energy_total, cycle_time, alarm, time.time()),
    )
    conn.commit()


def get_readings(furnace: str, limit: int = 200):
    rows = conn.execute(
        "SELECT * FROM readings WHERE furnace=? ORDER BY ts DESC LIMIT ?",
        (furnace, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def add_order(order_id, product, furnace, target_temp, duration_min, state, created_at):
    conn.execute(
        """
        INSERT OR REPLACE INTO production_orders
        (id, product, furnace, target_temp, duration_min, state, created_at,
         started_at, finished_at, energy_total_m3, cycle_time_s)
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)
        """,
        (order_id, product, furnace, target_temp, duration_min, state, created_at),
    )
    conn.commit()


def update_order(order_id: str, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE production_orders SET {cols} WHERE id = ?",
        (*fields.values(), order_id),
    )
    conn.commit()


# ---------- Sanal fabrika ----------
plant = Plant()

# ---------- API modelleri ----------
class OrderIn(BaseModel):
    product: str
    furnace: str
    target_temp: float
    duration_min: float


@app.get("/api/furnaces")
def list_furnaces():
    return plant.get_states()


@app.get("/api/furnaces/{name}")
def get_furnace(name: str):
    states = plant.get_states()
    if name not in states:
        return {"error": "Fırın bulunamadı"}
    return states[name]


@app.get("/api/orders")
def list_orders():
    return plant.get_orders()


@app.post("/api/orders")
def create_order(data: OrderIn):
    order_id = plant.create_order(
        product=data.product,
        furnace=data.furnace,
        target_temp=data.target_temp,
        duration_min=data.duration_min,
    )
    order = plant.get_order(order_id)
    add_order(
        order_id=order_id,
        product=order["product"],
        furnace=order["furnace"],
        target_temp=order["target_temp"],
        duration_min=order["duration_min"],
        state=order["state"],
        created_at=order["created_at"],
    )
    return {"id": order_id, "state": order["state"]}


@app.post("/api/orders/{order_id}/start")
def start_order(order_id: str, payload: dict):
    furnace = payload.get("furnace")
    if not furnace:
        return {"error": "furnace zorunlu"}
    if not plant.start_order(order_id, furnace):
        return {"error": "Emir başlatılamadı"}
    update_order(order_id, state="RUNNING", started_at=time.time())
    return {"ok": True, "order_id": order_id, "furnace": furnace}


@app.get("/api/readings/{furnace}")
def get_readings_api(furnace: str, limit: int = 200):
    return get_readings(furnace, limit)


# ---------- Simülasyon döngüsü ----------
import asyncio

async def simulation_loop():
    while True:
        await asyncio.sleep(1.0)
        plant.update(1.0)
        states = plant.get_states()
        for name, s in states.items():
            add_reading(
                furnace=name,
                temperature=s["temperature"],
                target_temperature=s["target_temperature"],
                status=s["status"],
                burner_on=s["burner_on"],
                gas_consumption=s["gas_consumption"],
                energy_total=s["energy_total"],
                cycle_time=s["cycle_time"],
                alarm=s["alarm"],
            )


@app.on_event("startup")
async def startup():
    asyncio.create_task(simulation_loop())
    asyncio.create_task(run_opcua_server(plant, host="0.0.0.0", port=4840))


# ---------- Frontend ----------
app.mount("/", StaticFiles(directory="erp_simulation/frontend", html=True), name="frontend")
