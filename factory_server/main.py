import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from factory_server.database import FactoryDB
from factory_server.plc_client import PLCManager

app = FastAPI(title="Fabrika Yerel ERP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB = FactoryDB("factory_erp.db")
PLC = PLCManager(DB)


@app.on_event("startup")
async def startup():
    asyncio.create_task(plc_loop())


async def plc_loop():
    while True:
        try:
            if not PLC.connected:
                found = PLC.scan_network()
                if found:
                    first = found[0]
                    PLC.connect_plc(
                        host=first["ip"],
                        port=int(first["port"]),
                        protocol=first["protocol"],
                    )
            else:
                PLC.poll_once()
        except Exception as e:
            print("PLC loop hata:", e)
        await asyncio.sleep(3)


# ---------- API ----------
@app.get("/api/machines")
def machines():
    return DB.get_machines()


@app.get("/api/readings/{machine_id}")
def readings(machine_id: str, limit: int = 100):
    return DB.get_readings(machine_id, limit)


@app.get("/api/latest/{machine_id}/{tag_name}")
def latest(machine_id: str, tag_name: str):
    return DB.get_latest_reading(machine_id, tag_name)


@app.post("/api/plc/connect")
def plc_connect(host: str, port: int = 502, protocol: str = "modbus"):
    ok = PLC.connect_plc(host, port, protocol)
    return {"ok": ok}


@app.get("/api/plc/scan")
def plc_scan():
    return PLC.scan_network()


# ---------- Frontend ----------
app.mount("/", StaticFiles(directory="factory_server/frontend", html=True), name="frontend")
