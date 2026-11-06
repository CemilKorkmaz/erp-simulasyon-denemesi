"""Sanal fırın termal ve işletme modeli.

Bu modül, fiziksel bir fırının bilgisayar ortamındaki davranışını taklit eder:

- Fırın kapalı iken sıcaklık yavaşça ortam sıcaklığına doğru düşer.
- Fırın çalıştırıldığında sıcaklık hedef sıcaklığa doğru yükselir.
- Hedef sıcaklığa ulaşıldığında termostat mantığıyla sıcaklık sabitlenir (bekletme).
- Isıtma durduğunda soğumaya başlar.
- Sıcaklık maksimum sınırı aştığında alarm oluşturulur.
- Brülör açıkken gaz/enerji tüketimi artar.

Tüm değerler saniyelik adımlarla (dt) güncellenir.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FurnaceStatus(Enum):
    OFF = "KAPALI"
    HEATING = "ISINIYOR"
    HOLDING = "BEKLETIYOR"   # hedefte tutuluyor (üretim çevrimi devam ediyor)
    COOLING = "SOGUYOR"
    ALARM = "ALARM"


@dataclass
class FurnaceParams:
    name: str
    furnace_type: str  # "ERITME", "HOMOJENIZASYON", "BIYET_ISITMA"
    ambient_temp: float = 25.0
    target_temp: float = 750.0
    max_temp: float = 850.0
    heat_rate: float = 2.0           # Maksimum ısaltma hizi (derece / saniye)
    cool_rate: float = 0.03          # Soğuma katsayısı (1/sn)
    hold_band: float = 5.0           # Bekletme bandı (derece)
    gas_consumption_full: float = 120.0  # Brülör açıkken m3/saat


@dataclass
class FurnaceState:
    temperature: float = 25.0
    target_temperature: float = 25.0
    status: FurnaceStatus = FurnaceStatus.OFF
    burner_on: bool = False
    gas_consumption: float = 0.0     # anlik m3/saat
    energy_total: float = 0.0        # kümülatif m3
    cycle_time: float = 0.0          # mevcut çevrimde geçen süre (saniye)
    alarm: Optional[str] = None
    last_updated: float = field(default_factory=time.time)


class Furnace:
    """Tek bir sanal fırın."""

    def __init__(self, params: FurnaceParams):
        self.params = params
        self.state = FurnaceState(
            temperature=params.ambient_temp,
            target_temperature=params.target_temp,
            status=FurnaceStatus.OFF,
        )
        # Bu fırına atanmış üretim emri (erp_backend tarafından yönetilir)
        self.order_id: Optional[str] = None
        self.order_product: Optional[str] = None
        self.order_duration_s: float = 0.0
        self.soak_started_at: Optional[float] = None

    def start_order(self, order_id: str, product: str, target_temp: float,
                    duration_min: float, now: float) -> None:
        """Üretim emriyle fırını çalıştırma moduna geçirir."""
        self.order_id = order_id
        self.order_product = product
        self.order_duration_s = duration_min * 60.0
        self.state.target_temperature = target_temp
        self.state.status = FurnaceStatus.HEATING
        self.state.cycle_time = 0.0
        self.soak_started_at = None
        self.state.alarm = None

    def complete_order(self) -> Optional[dict]:
        """Çevrim tamamlandıysa emri kapatır ve özet döndürür."""
        if self.order_id is None:
            return None
        summary = {
            "order_id": self.order_id,
            "product": self.order_product,
            "furnace": self.params.name,
            "furnace_type": self.params.furnace_type,
            "target_temperature": self.state.target_temperature,
            "cycle_time_s": self.state.cycle_time,
            "energy_total_m3": self.state.energy_total,
        }
        self.order_id = None
        self.order_product = None
        self.order_duration_s = 0.0
        self.soak_started_at = None
        self.state.status = FurnaceStatus.OFF
        self.state.target_temperature = self.params.target_temp
        self.state.cycle_time = 0.0
        return summary

    def update(self, dt: float) -> list[dict]:
        """Bir adım (dt saniye) simülasyonu ilerletir. Olası olayı döndürür."""
        events: list[dict] = []
        p = self.params
        s = self.state
        now = time.time()

        # ---- Durum makinesi ----
        if s.status == FurnaceStatus.ALARM:
            s.burner_on = False
            # Sıcaklık güvenli seviyeye düştüğünde alarm otomatik temizlenir,
            # fırın KAPALI durumuna döner.
            if s.temperature < p.max_temp - 10.0:
                s.status = FurnaceStatus.OFF
                s.alarm = None
                events.append({"type": "alarm_cleared", "furnace": p.name})
        elif s.status == FurnaceStatus.OFF:
            s.burner_on = False
        elif s.status == FurnaceStatus.HEATING:
            s.burner_on = True
            # Hedefe ulaşıldığında bekletmeye geç.
            if s.temperature >= s.target_temperature - p.hold_band:
                s.status = FurnaceStatus.HOLDING
                s.soak_started_at = now
                events.append({
                    "type": "target_reached",
                    "furnace": p.name,
                    "temperature": s.temperature,
                })
        elif s.status == FurnaceStatus.HOLDING:
            # Termostat: alt bandın altında ise ısıt, üst bandın üzeri kapat.
            if s.temperature < s.target_temperature - p.hold_band:
                s.burner_on = True
            elif s.temperature > s.target_temperature + p.hold_band:
                s.burner_on = False
            # Üretim süresi dolduysa emri tamamla.
            if (self.order_id is not None and self.soak_started_at is not None
                    and now - self.soak_started_at >= self.order_duration_s):
                summary = self.complete_order()
                if summary:
                    events.append({"type": "order_completed", "summary": summary})
        elif s.status == FurnaceStatus.COOLING:
            s.burner_on = False

        # ---- Alarm: şu anki sıcaklık zaten sınırın üstünde (örnek: sensör titresimi/artefakt) ----
        if s.temperature > p.max_temp and s.status != FurnaceStatus.ALARM:
            s.status = FurnaceStatus.ALARM
            s.burner_on = False
            s.alarm = (
                f"{p.name}: Aşırı sıcaklık alarmı! "
                f"{s.temperature:.1f} °C > {p.max_temp} °C"
            )
            events.append({"type": "alarm", "furnace": p.name,
                           "temperature": s.temperature, "message": s.alarm})

        # ---- Termal fizigi (birinci merkezli model) ----
        if s.burner_on and s.status in (FurnaceStatus.HEATING, FurnaceStatus.HOLDING):
            # Hedefe doğru yavaşlayan eğrili ısalama:
            # başlangıçta heat_rate, hedefe yaklaştıkça sıfıra iner.
            progress = (s.temperature - p.ambient_temp) / max(
                s.target_temperature - p.ambient_temp, 1.0)
            dT = p.heat_rate * max(0.0, 1.0 - progress) * dt * 0.55
        else:
            # Isıtma kapalıyken ortam sıcaklığına doğru çarpısmalı soğuma.
            dT = -p.cool_rate * (s.temperature - p.ambient_temp) * dt

        s.temperature += dT
        if s.temperature < p.ambient_temp:
            s.temperature = p.ambient_temp

        # ---- Tüketim ve enerji ----
        s.gas_consumption = p.gas_consumption_full if s.burner_on else 0.0
        s.energy_total += s.gas_consumption * (dt / 3600.0)
        if s.status in (FurnaceStatus.HEATING, FurnaceStatus.HOLDING):
            s.cycle_time += dt

        # ---- Alarm: aşırı sıcaklık ----
        if s.temperature > p.max_temp and s.status != FurnaceStatus.ALARM:
            s.status = FurnaceStatus.ALARM
            s.burner_on = False
            s.alarm = (
                f"{p.name}: Aşırı sıcaklık alarmı! "
                f"{s.temperature:.1f} °C > {p.max_temp} °C"
            )
            events.append({"type": "alarm", "furnace": p.name,
                           "temperature": s.temperature, "message": s.alarm})

        s.last_updated = now
        return events

    def to_dict(self) -> dict:
        s = self.state
        p = self.params
        return {
            "name": p.name,
            "type": p.furnace_type,
            "temperature": round(s.temperature, 2),
            "target_temperature": round(s.target_temperature, 2),
            "max_temperature": self.params.max_temp,
            "status": s.status.value,
            "status_kodu": s.status.name,
            "burner_on": s.burner_on,
            "gas_consumption": round(s.gas_consumption, 2),
            "energy_total": round(s.energy_total, 2),
            "cycle_time": round(s.cycle_time, 1),
            "alarm": s.alarm,
            "last_updated": s.last_updated,
            "order_id": self.order_id,
            "order_product": self.order_product,
        }


def p_max(p: FurnaceParams) -> float:  # yardımcı (to_dict okunurlugu icin)
    return p.max_temp
