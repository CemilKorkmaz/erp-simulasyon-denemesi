"""ERP backend: FastAPI arayüzü, OPC UA sunucusu, simülasyon döngüsü ve WebSocket.

Calistirmak icin (repo kokuundan):
    python3 -m erp_backend.main

Hızlandırmak için (test/demo):
    SIM_SPEED=10 python3 -m erp_backend.main
    # 10 => simülasyonda 1 saniyelik fizik, gerçekte 0.1 saniyede işlenir.
    # Fırın 30 dakikada alarm veriyorsa, SIM_SPEED=10 ile 3 dakikada verir.

Arayüz:  http://localhost:8000
OPC UA:  opc.tcp://localhost:4840/freeopcua/server/
"""

from __future__ import annotations

import asyncio
import os
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
from simulator.plc_writer import PlcWriteController, KONTROL_SINYALLERI
from simulator.faults import FaultInjector
from erp_backend.database import Database

# ------------------------------------------------------------------ ayarlar

# Simülasyon hız çarpanı. 1 = gerçek zamanlı. >1 = hızlandırılmış.
# Örn. SIM_SPEED=10 -> simülasyonda 1 sn, gerçekte 0.1 sn.
# Başlangıç değeri ortam değişkeninden okunur; arayüzden canlı değiştirilebilir.
DEFAULT_SPEED = max(0.1, float(os.environ.get("SIM_SPEED", "1")))
SIM_SPEED = DEFAULT_SPEED

HIZ_ADIMLARI = [1, 2, 5, 10, 25, 50]

# Gerçek zamanlı döngü adımı (saniye). Fizik adımı = LOOP_DT * SIM_SPEED
# olacak şekilde sabit tutulur, yani SIM_SPEED fizik modelini bozmaz.
LOOP_DT = 0.25

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
    fill_minutes=6.0,    # 750 °C'ye ~10.5 sim-dakikasında ulaşır
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
    fill_minutes=6.0,
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
    fill_minutes=6.0,
))


# ------------------------------------------------------------------ sanal PLC yazma

# ERP'nin fırınlara YAZMASINI test edebilmek için ters yön.
# Gerçek sahada bu kapalıdır; test için ERP_PLC_WRITE=1 ile açılır.
PLC = PlcWriteController(plant, enabled=os.environ.get("ERP_PLC_WRITE", "0") == "1")

# Arıza/kesinti enjeksiyonu (bayat veri, sensör hatası, aşırı sıcaklık...)
FAULTS = FaultInjector()


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
    """Döngü adımı: fırınları güncelle, veritabanına yaz, tarayıcılara yay.

    SIM_SPEED=1  -> saniyede 4 fizik adımı x 0.25 sn = gerçek zamanlı (1x)
    SIM_SPEED=10 -> saniyede 4 fizik adımı x 2.50 sn = 10 kat hızlı
    Fizik modeli (ısıtma eğrisi, alarm, reçete) aynı kalır; sadece zaman ilerler.
    """
    while True:
        await asyncio.sleep(LOOP_DT)
        # Ağ/PLC kesintisi: fizik ilerlemez, veri donar. Servis ayakta kalır.
        if FAULTS.state.offline:
            continue
        # Hız her adımda okunur: arayüzden değiştirilince hemen etki eder.
        events = plant.update(LOOP_DT * SIM_SPEED)

        states = plant.get_states()
        orders = plant.get_orders()

        # Çevrimi tamamlanan emirleri veritabanına da yansıt (özet bilgilerle).
        # Not: DB yazımı başarısız olsa bile canlı yayın (WebSocket) devam etsin;
        # eskiden burada oluşan bir hata tüm simülasyon döngüsünü durduruyordu.
        try:
            for event in events:
                if event.get("type") == "order_completed":
                    summary = event["summary"]
                    oid = summary["order_id"]
                    emir = plant.get_order(oid) or {}
                    # PLC üzerinden açılan emirlerde DB satırı olmayabilir;
                    # upsert için kimlik alanlarını da geçir.
                    DB.update_order(
                        oid,
                        state="COMPLETED",
                        finished_at=time.time(),
                        energy_total_m3=summary["energy_total_m3"],
                        cycle_time_s=summary["cycle_time_s"],
                        product=emir.get("product"),
                        furnace=emir.get("furnace"),
                        target_temp=emir.get("target_temp"),
                        duration_min=emir.get("duration_min"),
                        created_at=emir.get("created_at"),
                    )

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
        except Exception as exc:  # pragma: no cover - savunma amaçlı
            print("Veritabanı yazma hatası (canlı akış sürüyor):", exc)

        await manager.broadcast({
            "type": "tick",
            "ts": time.time(),
            "furnaces": states,
            "orders": orders,
        })


# ------------------------------------------------------------------ FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Önceki oturumdan yarıda kalan emirleri kapat (hayalet RUNNING kalmasın).
    try:
        kapatilan = DB.close_stale_orders()
        if kapatilan:
            print(f"Açılış: {kapatilan} yarıda kalan emir INTERRUPTED olarak kapatıldı.")
    except Exception as exc:  # pragma: no cover
        print("Yarıda kalan emirler kapatılamadı:", exc)
    asyncio.create_task(simulation_loop())
    asyncio.create_task(run_opcua_server(plant, host="0.0.0.0", port=4840))
    yield


app = FastAPI(title="ERP Fabrika Simülasyonu", lifespan=lifespan)

# Arayüz klasörü: normal çalışmada repo kökündeki "frontend",
# paketlenmiş (exe) çalışmada _MEIPASS içindeki kopya.
FRONTEND_DIR = os.environ.get("ERP_FRONTEND_DIR", "frontend")
INDEX_HTML = os.path.join(FRONTEND_DIR, "index.html")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")


class OrderIn(BaseModel):
    product: str
    furnace: str
    target_temp: float
    duration_min: float


@app.get("/")
async def index():
    return FileResponse(INDEX_HTML)


def durum_yaniti() -> dict:
    """Fırın durumları + veri kalitesi + bağlantı bilgisi.

    ERP bu yanıttaki `_meta.quality` alanına bakarak verinin GOOD/STALE/BAD
    olduğunu anlar (doküman §8.2). Kesintide `offline: true` döner.
    """
    states = plant.get_states()
    st = FAULTS.state
    for s in states.values():
        s["quality"] = st.quality
        s["simulated"] = True
        # Sensör hatasında ölçüm güvenilmez; alarm üretilmez (sadece BAD etiketi)
        if st.sensor_fault:
            s["sensor_ok"] = False
    return states


@app.get("/api/furnaces")
async def list_furnaces():
    if FAULTS.state.offline:
        raise HTTPException(503, "PLC bağlantısı yok (simülasyon kesintisi)")
    return durum_yaniti()


@app.get("/api/furnaces/{name}")
async def get_furnace(name: str):
    if FAULTS.state.offline:
        raise HTTPException(503, "PLC bağlantısı yok (simülasyon kesintisi)")
    states = durum_yaniti()
    if name not in states:
        raise HTTPException(status_code=404, detail="Fırın bulunamadı")
    return states[name]


@app.get("/api/meta")
async def api_meta():
    """ERP'nin tek çağrıda göreceği sağlık + kalite + yetenek bilgisi."""
    return {
        "health": not FAULTS.state.offline,
        "quality": FAULTS.state.quality,
        "offline": FAULTS.state.offline,
        "stale": FAULTS.state.stale,
        "sensor_fault": FAULTS.state.sensor_fault,
        "note": FAULTS.state.note,
        "sim_speed": SIM_SPEED,
        "plc_write": PLC.enabled,
        "furnaces": list(plant.furnaces),
        "version": "2.0-test",
    }

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


class SpeedIn(BaseModel):
    speed: float


@app.get("/api/speed")
async def get_speed():
    return {"speed": SIM_SPEED, "adimlar": HIZ_ADIMLARI}


@app.post("/api/speed")
async def set_speed(data: SpeedIn):
    global SIM_SPEED
    speed = max(0.1, min(float(data.speed), 100.0))
    SIM_SPEED = speed
    return {"speed": SIM_SPEED}


# ------------------------------------------------------------------ arıza enjeksiyonu
#
# ERP'nizi kötü senaryolara hazırlamak için. Hepsi tek çağrıyla açılır/kapanır.


@app.get("/api/test/faults")
async def test_faults():
    return FAULTS.snapshot()


@app.post("/api/test/faults/offline")
async def test_fault_offline(payload: dict | None = None):
    """PLC/ağ kesintisi: veri akışı durur, uçlar 503 döner."""
    p = payload or {}
    return FAULTS.set_offline(bool(p.get("aktif", True)), p.get("note", ""))


@app.post("/api/test/faults/stale")
async def test_fault_stale(payload: dict | None = None):
    """Bayat veri: servis ayakta ama yeni ölçüm gelmiyor (STALE)."""
    p = payload or {}
    return FAULTS.set_stale(bool(p.get("aktif", True)), p.get("note", ""))


@app.post("/api/test/faults/sensor")
async def test_fault_sensor(payload: dict | None = None):
    """Sensör hatası: sıcaklık okuması BAD."""
    p = payload or {}
    return FAULTS.set_sensor_fault(bool(p.get("aktif", True)), p.get("note", ""))


@app.post("/api/test/faults/overheat")
async def test_fault_overheat(payload: dict | None = None):
    """Fırını güvenlik sınırının üstüne çıkar (alarm testi)."""
    p = payload or {}
    furnace = p.get("furnace") or next(iter(plant.furnaces))
    return FAULTS.overheat(plant, furnace, float(p.get("fazla", 25)))


@app.post("/api/test/faults/power-loss")
async def test_fault_power_loss():
    """Güç kesintisi: tüm fırınlar KAPALI'ya düşer."""
    return FAULTS.power_loss(plant)


@app.post("/api/test/faults/clear")
async def test_fault_clear():
    """Tüm arızaları temizle."""
    return FAULTS.clear_all()


# ------------------------------------------------------------------ sanal PLC uçları
#
# Doküman §8: gerçek sahada ERP **okur**, PLC'ye **yazmaz**.
# Simülasyonda ise "ERP'den fırına emir" tarafını da test edebilmen için
# ters yön açılır. Varsayılan KAPALIDIR; ERP_PLC_WRITE=1 ile açılır.


@app.get("/api/plc/health")
async def plc_health():
    """PLC yazma yeteneği açık mı? ERP'niz bunu kontrol edebilir."""
    return {
        "yazma_aktif": PLC.enabled,
        "aciklama": "Kapalıysa sadece okuma yapılabilir (üretim önerisi)",
        "sinyaller": list(KONTROL_SINYALLERI),
        "furnaces": list(plant.furnaces),
        "nasil_acilir": "Sunucuyu ERP_PLC_WRITE=1 ile başlat",
    }


@app.get("/api/plc/snapshot")
async def plc_snapshot():
    """SCADA benzeri tam görüntü: dört sinyal + telemetri + son komutlar."""
    return PLC.snapshot()


@app.get("/api/plc/signals")
async def plc_signals():
    return PLC.read_all_signals()


@app.get("/api/plc/commands")
async def plc_commands(limit: int = 50):
    """Son yazma komutlarının kaydı (kim, ne zaman, sonuç)."""
    return [c.to_dict() for c in PLC.commands[-limit:]][::-1]


@app.post("/api/plc/set-target")
async def plc_set_target(payload: dict):
    furnace = payload.get("furnace")
    target = payload.get("target")
    if not furnace or target is None:
        raise HTTPException(400, "furnace ve target alanları zorunlu")
    cmd = PLC.set_target(furnace, float(target), source=payload.get("source", "ERP"))
    if not cmd.ok:
        raise HTTPException(400, cmd.message)
    return cmd.to_dict()


@app.post("/api/plc/start")
async def plc_start(payload: dict):
    furnace = payload.get("furnace")
    if not furnace:
        raise HTTPException(400, "furnace alanı zorunlu")
    cmd = PLC.start(
        furnace,
        source=payload.get("source", "ERP"),
        product=payload.get("product", "ERP Emri"),
        duration_min=float(payload.get("duration_min", 5)),
        target=payload.get("target"),
    )
    if not cmd.ok:
        raise HTTPException(400, cmd.message)
    # Emri hemen veritabanına işle: tamamlanınca update_order satırı bulsun.
    oid = (cmd.sonuc or {}).get("order_id") if isinstance(cmd.sonuc, dict) else None
    if oid:
        emir = plant.get_order(oid) or {}
        DB.add_order(
            order_id=oid,
            product=emir.get("product") or "ERP Emri",
            furnace=furnace,
            target_temp=float(emir.get("target_temp") or 0.0),
            duration_min=float(emir.get("duration_min") or 0.0),
            state="RUNNING",
            created_at=float(emir.get("created_at") or time.time()),
        )
    return cmd.to_dict()


@app.post("/api/plc/stop")
async def plc_stop(payload: dict):
    furnace = payload.get("furnace")
    if not furnace:
        raise HTTPException(400, "furnace alanı zorunlu")
    cmd = PLC.stop(furnace, source=payload.get("source", "ERP"))
    if not cmd.ok:
        raise HTTPException(400, cmd.message)
    return cmd.to_dict()


@app.post("/api/plc/reset-alarm")
async def plc_reset_alarm(payload: dict):
    furnace = payload.get("furnace")
    if not furnace:
        raise HTTPException(400, "furnace alanı zorunlu")
    cmd = PLC.reset_alarm(furnace, source=payload.get("source", "ERP"))
    if not cmd.ok:
        raise HTTPException(400, cmd.message)
    return cmd.to_dict()


@app.post("/api/plc/signals")
async def plc_write_signals(payload: dict):
    furnace = payload.get("furnace")
    signals = payload.get("signals")
    if not furnace or not isinstance(signals, dict):
        raise HTTPException(400, "furnace ve signals sözlüğü zorunlu")
    cmd = PLC.set_signals(furnace, signals, source=payload.get("source", "ERP"))
    if not cmd.ok:
        raise HTTPException(400, cmd.message)
    return cmd.to_dict()


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


def run(port: int = 8000, host: str = "0.0.0.0") -> None:
    """Sunucuyu çalıştırır. Hem `python -m` hem exe başlatıcı bunu kullanır."""
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
