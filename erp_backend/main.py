"""ERP backend: FastAPI arayüzü, OPC UA sunucusu, simülasyon döngüsü ve WebSocket.

Calistirmak icin (repo kokuundan):
    python3 -m erp_backend.main

Arayüz:  http://localhost:8000
OPC UA:  opc.tcp://localhost:4840/freeopcua/server/
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from simulator.plant import Plant
from simulator.opcua_server import run_opcua_server
from simulator.furnace import FurnaceParams
from erp_backend.database import Database

# ------------------------------------------------------------------ veritabani

DB = Database("erp_sim.db")

# ------------------------------------------------------------------ sanal fabrika

plant = Plant()

# Rehberdeki üç ekipman: eritme, homojenizasyon ve biyet ısıtma fırınları.
plant.add_furnace(FurnaceParams(
    name="Aluminyum Eritme Fırını",
    furnace_type="ERITME",
    ambient_temp=25.0,
    target_temp=750.0,
    max_temp=850.0,
    heat_rate=2.5,
    cool_rate=0.03,
    hold_band=5.0,
    gas_consumption_full=120.0,
))
plant.add_furnace(FurnaceParams(
    name="Homojenizasyon Fırını",
    furnace_type="HOMOJENIZASYON",
    ambient_temp=25.0,
    target_temp=560.0,
    max_temp=620.0,
    heat_rate=1.2,
    cool_rate=0.03,
    hold_band=4.0,
    gas_consumption_full=80.0,
))
plant.add_furnace(FurnaceParams(
    name="Biyet Isıtma Fırını",
    furnace_type="BIYET_ISITMA",
    ambient_temp=25.0,
    target_temp=480.0,
    max_temp=540.0,
    heat_rate=1.8,
    cool_rate=0.03,
    hold_band=4.0,
    gas_consumption_full=60.0,
))


# ------------------------------------------------------------------ websocket

class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        if not self.active:
            return
        import json
        data = json.dumps(message, default=str)
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# ------------------------------------------------------------------ simülasyon döngüsü

async def simulation_loop() -> None:
    """Her saniye: fırınları güncelle, veritabanına yaz, tarayıcılara yay."""
    while True:
        await asyncio.sleep(1.0)
        plant.update(1.0)
        states = plant.get_states()
        orders = plant.get_orders()

        for name, s in states.items():
            DB.add_reading(
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

        await manager.broadcast({
            "type": "tick",
            "ts": time.time(),
            "furnaces": states,
            "orders": orders,
        })


# ------------------------------------------------------------------ FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(simulation_loop())
    asyncio.create_task(run_opcua_server(plant, host="0.0.0.0", port=4840))
    yield


app = FastAPI(title="ERP Fabrika Simülasyonu", lifespan=lifespan)

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")


class OrderIn(BaseModel):
    product: str
    furnace: str
    target_temp: float
    duration_min: float


@app.get("/")
async def index():
    return FileResponse("frontend/index.html")


@app.get("/api/furnaces")
async def list_furnaces():
    return plant.get_states()


@app.get("/api/furnaces/{name}")
async def get_furnace(name: str):
    states = plant.get_states()
    if name not in states:
        raise HTTPException(status_code=404, detail="Fırın bulunamadı")
    return states[name]


@app.get("/api/orders")
async def list_orders():
    return plant.get_orders()


@app.post("/api/orders")
async def create_order(data: OrderIn):
    order_id = plant.create_order(
        product=data.product,
        furnace=data.furnace,
        target_temp=data.target_temp,
        duration_min=data.duration_min,
    )
    order = plant.get_order(order_id)
    DB.add_order(
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
async def start_order(order_id: str, payload: dict):
    furnace = payload.get("furnace")
    if not furnace:
        raise HTTPException(status_code=400, detail="furnace alanı zorunlu")
    if not plant.start_order(order_id, furnace):
        raise HTTPException(
            status_code=400,
            detail="Emir başlatılamadı (geçersiz id, zaten çalışıyor veya fırın meşgul)",
        )
    DB.update_order(order_id, state="RUNNING", started_at=time.time())
    return {"ok": True, "order_id": order_id, "furnace": furnace}


@app.get("/api/readings/{furnace}")
async def get_readings(furnace: str, limit: int = 200):
    return DB.get_readings(furnace, limit)


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # İstemciden mesaj beklemiyoruz; bağlantıyı açık tutmak için.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if __name__ == "__main__":
    uvicorn.run("erp_backend.main:app", host="0.0.0.0", port=8000)
