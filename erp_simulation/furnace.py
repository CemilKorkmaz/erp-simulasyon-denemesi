"""Sanal fırın termal ve işletme modeli.

Davranış:
- Kapalı iken sıcaklık ortam sıcaklığına doğru düşer.
- Çalışırken hedef sıcaklığa doğru yükselir.
- Hedefe ulaştığında termostatla sabit tutulur (bekletme).
- Sıcaklık max_temp'i aşarsa ALARM düşer ve brülör kapanır.
- Brülör açıkken gaz tüketimi artar.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FurnaceStatus(Enum):
    OFF = "KAPALI"
    HEATING = "ISINIYOR"
    HOLDING = "BEKLETIYOR"
    COOLING = "SOGUYOR"
    ALARM = "ALARM"


@dataclass
class FurnaceState:
    temperature: float = 25.0
    target_temperature: float = 25.0
    status: FurnaceStatus = FurnaceStatus.OFF
    burner_on: bool = False
    gas_consumption: float = 0.0
    energy_total: float = 0.0
    cycle_time: float = 0.0
    alarm: Optional[str] = None
    last_updated: float = field(default_factory=time.time)
    order_id: Optional[str] = None
    order_product: Optional[str] = None
    order_duration_s: float = 0.0
    soak_started_at: Optional[float] = None


class Furnace:
    def __init__(self, config):
        self.config = config
        self.state = FurnaceState(
            temperature=config.ambient_temp,
            target_temperature=config.target_temp,
        )
        # Simülasyon saati (gerçek saat değil). update(dt) ile ilerler; bekleme
        # süresi bu saatle ölçülür ki SIM_SPEED hızlandırması reçeteyi de kısaltır.
        self.sim_time: float = 0.0

    def start_order(self, order_id: str, product: str, target_temp: float,
                    duration_min: float, now: float) -> None:
        self.state.order_id = order_id
        self.state.order_product = product
        self.state.target_temperature = target_temp
        self.state.order_duration_s = duration_min * 60.0
        self.state.status = FurnaceStatus.HEATING
        self.state.cycle_time = 0.0
        self.state.soak_started_at = None
        self.state.alarm = None

    def complete_order(self) -> Optional[dict]:
        if self.state.order_id is None:
            return None
        summary = {
            "order_id": self.state.order_id,
            "product": self.state.order_product,
            "furnace": self.config.name,
            "type": self.config.furnace_type,
            "target_temperature": self.state.target_temperature,
            "cycle_time_s": self.state.cycle_time,
            "energy_total_m3": self.state.energy_total,
        }
        self.state.order_id = None
        self.state.order_product = None
        self.state.order_duration_s = 0.0
        self.state.status = FurnaceStatus.OFF
        self.state.target_temperature = self.config.target_temp
        self.state.cycle_time = 0.0
        self.state.soak_started_at = None
        return summary

    def update(self, dt: float) -> list[dict]:
        events: list[dict] = []
        c = self.config
        s = self.state
        self.sim_time += dt
        now = time.time()

        if s.status == FurnaceStatus.ALARM:
            s.burner_on = False
            if s.temperature < c.max_temp - 10.0:
                s.status = FurnaceStatus.OFF
                s.alarm = None
                events.append({"type": "alarm_cleared", "furnace": c.name})
        elif s.status == FurnaceStatus.OFF:
            s.burner_on = False
        elif s.status == FurnaceStatus.HEATING:
            s.burner_on = True
            if s.temperature >= s.target_temperature - c.hold_band:
                s.status = FurnaceStatus.HOLDING
                s.soak_started_at = self.sim_time
                events.append({
                    "type": "target_reached",
                    "furnace": c.name,
                    "temperature": s.temperature,
                })
        elif s.status == FurnaceStatus.HOLDING:
            if s.temperature < s.target_temperature - c.hold_band:
                s.burner_on = True
            elif s.temperature > s.target_temperature + c.hold_band:
                s.burner_on = False
            if (s.order_id is not None and s.soak_started_at is not None
                    and self.sim_time - s.soak_started_at >= s.order_duration_s):
                summary = self.complete_order()
                if summary:
                    events.append({"type": "order_completed", "summary": summary})
        elif s.status == FurnaceStatus.COOLING:
            s.burner_on = False

        if s.burner_on and s.status in (FurnaceStatus.HEATING, FurnaceStatus.HOLDING):
            progress = (s.temperature - c.ambient_temp) / max(
                s.target_temperature - c.ambient_temp, 1.0
            )
            dT = c.heat_rate * max(0.0, 1.0 - progress) * dt * 0.55
        else:
            dT = -c.cool_rate * (s.temperature - c.ambient_temp) * dt

        s.temperature += dT
        if s.temperature < c.ambient_temp:
            s.temperature = c.ambient_temp

        s.gas_consumption = c.gas_consumption_full if s.burner_on else 0.0
        s.energy_total += s.gas_consumption * (dt / 3600.0)
        if s.status in (FurnaceStatus.HEATING, FurnaceStatus.HOLDING):
            s.cycle_time += dt

        if s.temperature > c.max_temp and s.status != FurnaceStatus.ALARM:
            s.status = FurnaceStatus.ALARM
            s.burner_on = False
            s.alarm = (
                f"{c.name}: Aşırı sıcaklık! {s.temperature:.1f} °C > {c.max_temp} °C"
            )
            events.append({"type": "alarm", "furnace": c.name,
                           "temperature": s.temperature, "message": s.alarm})

        s.last_updated = now
        return events

    def to_dict(self) -> dict:
        s = self.state
        c = self.config
        return {
            "name": c.name,
            "type": c.furnace_type,
            "temperature": round(s.temperature, 2),
            "target_temperature": round(s.target_temperature, 2),
            "max_temperature": c.max_temp,
            "status": s.status.value,
            "status_kodu": s.status.name,
            "burner_on": s.burner_on,
            "gas_consumption": round(s.gas_consumption, 2),
            "energy_total": round(s.energy_total, 2),
            "cycle_time": round(s.cycle_time, 1),
            "alarm": s.alarm,
            "last_updated": s.last_updated,
            "order_id": s.order_id,
            "order_product": s.order_product,
        }
