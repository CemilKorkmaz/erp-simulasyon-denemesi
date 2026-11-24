"""Arıza, kesinti ve veri kalitesi enjeksiyonu.

ERP'nizi gerçek hayatın kötü senaryolarına hazırlamak için:

* **Ağ/PLC kesintisi** (`offline`): veri üretimi durur, uçlar 503 döner.
  Arayüz çökmemeli, son görüntüyü `stale` etiketiyle gösterebilmelidir.
* **Bayat veri** (`stale`): değerler donar ama servis ayakta kalır; ERP
  tarafı `STALE` kalite etiketini görmelidir.
* **Sensör hatası** (`sensor_fault`): sıcaklık `BAD` işaretlenir, ölçüm
  güvenilmez. Gerçek sensör kopukluğuna karşılık gelir.
* **Aşırı sıcaklık** (`overheat`): fırın güvenlik sınırının üstüne çıkarılır;
  PLC alarm verir ve brülör kapanır (doküman §6.2/3).
* **Güç kesintisi** (`power_loss`): fırınlar KAPALI'ya düşer, sıcaklık
  soğumaya başlar — yeniden başlatma sonrası davranışı test edilir.

Her arıza bir **zaman damgası ve gerekçe** ile kaydedilir; ERP hangi verinin
neden şüpheli olduğunu görebilir.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FaultState:
    offline: bool = False
    stale: bool = False
    sensor_fault: bool = False
    note: str = ""
    since: float = 0.0
    # Uç noktaların döndüreceği kalite etiketi
    quality: str = "GOOD"

    def to_dict(self) -> dict:
        return {
            "offline": self.offline,
            "stale": self.stale,
            "sensor_fault": self.sensor_fault,
            "note": self.note,
            "since": self.since,
            "since_saat": time.strftime("%H:%M:%S", time.localtime(self.since)) if self.since else None,
            "quality": self.quality,
        }


class FaultInjector:
    """Arıza durumlarını tutar ve olay kaydı üretir."""

    def __init__(self) -> None:
        self.state = FaultState()
        self.log: list[dict] = []
        self._frozen: dict[str, dict] = {}

    # ------------------------------------------------------------- iç

    def _olay(self, olay: str, mesaj: str, kalite: str) -> dict:
        kayit = {
            "ts": time.time(),
            "saat": time.strftime("%H:%M:%S"),
            "olay": olay,
            "mesaj": mesaj,
            "kalite": kalite,
        }
        self.log.append(kayit)
        if len(self.log) > 200:
            del self.log[:-200]
        return kayit

    # ------------------------------------------------------------- komutlar

    def set_offline(self, aktif: bool, note: str = "") -> dict:
        self.state.offline = bool(aktif)
        self.state.since = time.time() if aktif else 0.0
        self.state.quality = "BAD" if aktif else ("STALE" if self.state.stale else "GOOD")
        self.state.note = note or ("PLC/ağ bağlantısı koptu (simülasyon)" if aktif else "Bağlantı düzeldi")
        if aktif:
            self.state.stale = False
            self.state.sensor_fault = False
        return self._olay("offline" if aktif else "offline_cleared",
                          self.state.note, self.state.quality)

    def set_stale(self, aktif: bool, note: str = "") -> dict:
        self.state.stale = bool(aktif)
        self.state.since = time.time() if aktif else 0.0
        if aktif:
            self.state.quality = "STALE"
            self.state.note = note or "Veri dondu: yeni ölçüm gelmiyor (STALE)"
        else:
            self.state.quality = "GOOD"
            self.state.note = note or "Veri akışı normale döndü"
        return self._olay("stale" if aktif else "stale_cleared",
                          self.state.note, self.state.quality)

    def set_sensor_fault(self, aktif: bool, note: str = "") -> dict:
        self.state.sensor_fault = bool(aktif)
        self.state.since = time.time() if aktif else 0.0
        if aktif:
            self.state.quality = "BAD"
            self.state.note = note or "Sensör hatası: sıcaklık okuması güvenilmez (BAD)"
        else:
            self.state.quality = "GOOD"
            self.state.note = note or "Sensör düzeldi"
        return self._olay("sensor_fault" if aktif else "sensor_fault_cleared",
                          self.state.note, self.state.quality)

    def overheat(self, plant, furnace: str, fazla: float = 25.0) -> dict:
        """Fırını güvenlik sınırının üstüne çıkarır (alarm testi)."""
        f = plant.furnaces.get(furnace)
        if not f:
            return self._olay("overheat_failed", f"Fırın bulunamadı: {furnace}", self.state.quality)
        f.state.temperature = f.params.max_temp + fazla
        return self._olay(
            "overheat",
            f"{furnace}: sıcaklık {f.state.temperature:.0f} °C'ye çekildi "
            f"(sınır {f.params.max_temp:.0f} °C) — alarm beklenir",
            self.state.quality,
        )

    def power_loss(self, plant) -> dict:
        """Güç kesintisi: fırınlar KAPALI'ya düşer."""
        for name, f in plant.furnaces.items():
            f.order_id = None
            f.order_product = None
            f.state.burner_on = False
            f.state.alarm = None
            f.state.status = type(f.state.status).OFF
        return self._olay("power_loss", "Güç kesintisi: tüm fırınlar KAPALI'ya düştü",
                          self.state.quality)

    def clear_all(self, note: str = "") -> dict:
        self.state.offline = False
        self.state.stale = False
        self.state.sensor_fault = False
        self.state.quality = "GOOD"
        self.state.since = 0.0
        self.state.note = note or "Tüm arızalar temizlendi"
        self._frozen.clear()
        return self._olay("clear_all", self.state.note, "GOOD")

    # ------------------------------------------------------------- okuma

    def snapshot(self) -> dict:
        return {"state": self.state.to_dict(), "log": self.log[-30:][::-1]}
