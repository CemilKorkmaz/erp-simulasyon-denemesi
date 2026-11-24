"""ERP (şef) → Sanal PLC (saha) yazma katmanı.

Bu dosyanın varlık sebebi
-------------------------
Dokümandaki sistem yalnızca **okur** (PLC'ye yazmaz) — gerçek fabrikada
güvenlik için doğru olan budur. Ama ERP'nin "fırına emir ver" tarafını da
test edebilmen için simülasyonda **ters yön** de açılır:

    ERP  ->  /api/plc/*  ->  Sanal PLC
    
Gerçek sahada bu katmanın karşılığı: ERP'nin yazma yetkisi OLMAMASI.
Bu yüzden:

* Her yazma **varsayılan olarak KAPALIDIR** (`ERP_PLC_WRITE=1` ile açılır).
* Her yazma bir **komut kaydı** üretir (kim, ne zaman, neyi, sonuç).
* Simülasyonun kendi iç kuralları **korunur**: örn. güvenlik sınırının
  (max_temp) üstünü hedef vermek istersen PLC bunu REDDEDER — aynen
  gerçek bir PLC'nin interlokunun yapacağı gibi.
* Yazma reddedilirse cevap `ok: false` + Türkçe gerekçe döner; ERP tarafı
  bunu test edebilir.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

# Dört kontrol sinyali (doküman §8.1) — PLC tarafında okunur, ERP yazar.
KONTROL_SINYALLERI = ("door", "casting", "alarm", "running")

# Fırın durumu -> dört sinyal eslemesi
#   running : fırın çalışıyor mu (brülör/çevrim var mı)
#   casting : döküm/devrilme modunda mı (BEKLETIYOR = hedefte tutuluyor)
#   alarm   : alarm var mı
#   door    : simülasyonda sensör yok -> None (doküman §15.1/6: "unknown")
SINYAL_ACIKLAMA = {
    "running": "Fırın çevrimde mi (brülör açık / ısınıyor)",
    "casting": "Döküm modu (hedef sıcaklıkta bekletme)",
    "alarm": "Alarm aktif mi",
    "door": "Kapı sensörü (simülasyonda yok → unknown)",
}


@dataclass
class PlcCommand:
    """Bir yazma denemesinin kaydı."""
    seq: int
    ts: float
    source: str          # "ERP" / "SCADA" / "TEST"
    action: str          # set_target / start / stop / reset_alarm / set_signals
    furnace: str
    payload: dict
    ok: bool
    message: str
    istenen: Any = None
    sonuc: Any = None

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "saat": time.strftime("%H:%M:%S", time.localtime(self.ts)),
            "source": self.source,
            "action": self.action,
            "furnace": self.furnace,
            "payload": self.payload,
            "ok": self.ok,
            "message": self.message,
            "istenen": self.istenen,
            "sonuc": self.sonuc,
        }


class PlcWriteController:
    """Sanal fırınlara ERP adına yazma yapan denetleyici.

    `enabled=False` iken bütün yazmalar `403` mantığıyla reddedilir
    (doküman §8: "PLC'ye yazılmaz" — varsayılan davranış).
    """

    def __init__(self, plant, enabled: bool = False) -> None:
        self.plant = plant
        self.enabled = enabled
        self.commands: list[PlcCommand] = []
        self._seq = 0
        # ERP'nin yazabildiği ek sinyaller (gerçek PLC'de tag olurdu)
        self.signals: dict[str, dict[str, Optional[bool]]] = {
            name: {"door": None, "casting": None, "alarm": None, "running": None}
            for name in plant.furnaces
        }
        # ERP'nin verdiği ve uygulanan hedef sıcaklıklar (start emrinde kullanılır)
        self.erp_targets: dict[str, float] = {}
        self._start_seq = 0

    # ---------------------------------------------------------------- iç

    def _kaydet(self, source: str, action: str, furnace: str, payload: dict,
                ok: bool, message: str, istenen: Any = None,
                sonuc: Any = None) -> PlcCommand:
        self._seq += 1
        cmd = PlcCommand(
            seq=self._seq, ts=time.time(), source=source, action=action,
            furnace=furnace, payload=payload, ok=ok, message=message,
            istenen=istenen, sonuc=sonuc,
        )
        self.commands.append(cmd)
        if len(self.commands) > 500:
            del self.commands[:-500]
        return cmd

    def _firin(self, name: str):
        return self.plant.furnaces.get(name)

    # ---------------------------------------------------------------- yazma

    def set_target(self, furnace: str, target: float, source: str = "ERP"):
        """Hedef sıcaklığı yazar. Güvenlik sınırı üstü REDDEDİLİR."""
        if not self.enabled:
            return self._kaydet(source, "set_target", furnace,
                                {"target": target}, False,
                                "PLC yazma kapalı (ERP_PLC_WRITE=1 ile açılır)",
                                istenen=target)
        f = self._firin(furnace)
        if not f:
            return self._kaydet(source, "set_target", furnace,
                                {"target": target}, False,
                                f"Fırın bulunamadı: {furnace}", istenen=target)
        if not isinstance(target, (int, float)):
            return self._kaydet(source, "set_target", furnace,
                                {"target": target}, False,
                                "Hedef sayısal olmalı", istenen=target)
        if target > f.params.max_temp:
            return self._kaydet(
                source, "set_target", furnace, {"target": target}, False,
                f"REDDEDİLDİ: {target:.0f} °C güvenlik sınırını "
                f"({f.params.max_temp:.0f} °C) aşıyor. PLC interlok devrede.",
                istenen=target, sonuc=f.state.target_temperature,
            )
        if target < f.params.ambient_temp:
            return self._kaydet(
                source, "set_target", furnace, {"target": target}, False,
                f"REDDEDİLDİ: {target:.0f} °C ortam sıcaklığının altında.",
                istenen=target, sonuc=f.state.target_temperature,
            )
        onceki = f.state.target_temperature
        f.state.target_temperature = float(target)
        self.erp_targets[furnace] = float(target)
        return self._kaydet(source, "set_target", furnace,
                            {"target": target}, True,
                            f"Hedef {target:.0f} °C yazıldı (önce {onceki:.0f} °C)",
                            istenen=target, sonuc=float(target))

    def start(self, furnace: str, source: str = "ERP", product: str = "ERP Emri",
              duration_min: float = 5.0, target: Optional[float] = None):
        """Fırını çalıştırır (start_order)."""
        if not self.enabled:
            return self._kaydet(source, "start", furnace, {}, False,
                                "PLC yazma kapalı (ERP_PLC_WRITE=1 ile açılır)")
        f = self._firin(furnace)
        if not f:
            return self._kaydet(source, "start", furnace, {}, False,
                                f"Fırın bulunamadı: {furnace}")
        if f.order_id is not None:
            return self._kaydet(
                source, "start", furnace, {}, False,
                f"REDDEDİLDİ: fırın meşgul (aktif emir {f.order_id})")
        hedef = target if target is not None else self.erp_targets.get(
            furnace, f.state.target_temperature)
        if hedef > f.params.max_temp:
            return self._kaydet(
                source, "start", furnace, {"target": hedef}, False,
                f"REDDEDİLDİ: hedef {hedef:.0f} °C güvenlik sınırını "
                f"({f.params.max_temp:.0f} °C) aşıyor", istenen=hedef)
        self._start_seq += 1
        f.start_order(order_id=f"PLC-{int(time.time())}-{self._start_seq}",
                      product=product, target_temp=float(hedef),
                      duration_min=float(duration_min), now=time.time())
        return self._kaydet(source, "start", furnace,
                            {"target": hedef, "duration_min": duration_min}, True,
                            f"Fırın başlatıldı, hedef {hedef:.0f} °C, "
                            f"süre {duration_min:g} dk", sonuc=hedef)

    def stop(self, furnace: str, source: str = "ERP"):
        """Fırını durdurur (emri iptal eder, KAPALI'ya döner)."""
        if not self.enabled:
            return self._kaydet(source, "stop", furnace, {}, False,
                                "PLC yazma kapalı (ERP_PLC_WRITE=1 ile açılır)")
        f = self._firin(furnace)
        if not f:
            return self._kaydet(source, "stop", furnace, {}, False,
                                f"Fırın bulunamadı: {furnace}")
        f.order_id = None
        f.order_product = None
        f.state.status = type(f.state.status).OFF
        f.state.burner_on = False
        # Alarm mandallıdır: stop alarmı SİLMEZ, sadece soğumaya bırakır.
        f.state.target_temperature = f.params.target_temp
        return self._kaydet(source, "stop", furnace, {}, True,
                            "Fırın durduruldu (KAPALI). Not: alarm varsa "
                            "soğuduktan sonra reset-alarm ile onaylanmalı.")

    def reset_alarm(self, furnace: str, source: str = "ERP"):
        """Alarmı temizler (fırın sıcaklığı güvenli seviyeye inmişse)."""
        if not self.enabled:
            return self._kaydet(source, "reset_alarm", furnace, {}, False,
                                "PLC yazma kapalı (ERP_PLC_WRITE=1 ile açılır)")
        f = self._firin(furnace)
        if not f:
            return self._kaydet(source, "reset_alarm", furnace, {}, False,
                                f"Fırın bulunamadı: {furnace}")
        if f.state.alarm is None:
            return self._kaydet(source, "reset_alarm", furnace, {}, True,
                                "Aktif alarm yok (değişiklik yapılmadı)")
        if not f.reset_alarm():
            return self._kaydet(
                source, "reset_alarm", furnace, {}, False,
                f"REDDEDİLDİ: sıcaklık hâlâ yüksek "
                f"({f.state.temperature:.0f} °C). Önce soğumasını bekle "
                f"(güvenli seviye {f.params.max_temp - 10:.0f} °C altı).")
        return self._kaydet(source, "reset_alarm", furnace, {}, True,
                            "Alarm onaylandı (mandal açıldı), fırın KAPALI")

    def set_signals(self, furnace: str, signals: dict, source: str = "ERP"):
        """Dört kontrol sinyalini yazar (yoklama/test amaçlı)."""
        if not self.enabled:
            return self._kaydet(source, "set_signals", furnace, signals, False,
                                "PLC yazma kapalı (ERP_PLC_WRITE=1 ile açılır)")
        f = self._firin(furnace)
        if not f:
            return self._kaydet(source, "set_signals", furnace, signals, False,
                                f"Fırın bulunamadı: {furnace}")
        gecersiz = [k for k in signals if k not in KONTROL_SINYALLERI]
        if gecersiz:
            return self._kaydet(source, "set_signals", furnace, signals, False,
                                f"REDDEDİLDİ: bilinmeyen sinyal {gecersiz}. "
                                f"Geçerli: {list(KONTROL_SINYALLERI)}")
        self.signals.setdefault(furnace, {})
        for k, v in signals.items():
            self.signals[furnace][k] = v
        return self._kaydet(source, "set_signals", furnace, signals, True,
                            f"Sinyaller yazıldı: {signals}")

    # ---------------------------------------------------------------- okuma

    def read_signals(self, furnace: str) -> dict:
        """Dört sinyalin güncel durumu (simülasyondan türetilir)."""
        f = self._firin(furnace)
        if not f:
            return {}
        s = f.state
        yazilan = self.signals.get(furnace, {})
        running = bool(s.burner_on or s.status.name in ("HEATING", "HOLDING"))
        casting = s.status.name == "HOLDING"
        alarm = s.alarm is not None
        return {
            "running": yazilan.get("running") if yazilan.get("running") is not None else running,
            "casting": yazilan.get("casting") if yazilan.get("casting") is not None else casting,
            "alarm": yazilan.get("alarm") if yazilan.get("alarm") is not None else alarm,
            "door": yazilan.get("door"),   # simülasyonda sensör yok
        }

    def read_all_signals(self) -> dict:
        return {name: self.read_signals(name) for name in self.plant.furnaces}

    def snapshot(self) -> dict:
        """SCADA benzeri tam görüntü: sinyaller + telemetri + son komutlar."""
        out = {}
        for name, f in self.plant.furnaces.items():
            s = f.state
            out[name] = {
                "signals": self.read_signals(name),
                "telemetry": {
                    "sicaklik": round(s.temperature, 1),
                    "hedef": round(s.target_temperature, 1),
                    "maks": f.params.max_temp,
                    "gaz_m3_saat": round(s.gas_consumption, 1),
                    "enerji_m3": round(s.energy_total, 2),
                    "cevrim_sn": round(s.cycle_time, 0),
                },
                "durum": s.status.value,
                "alarm": s.alarm,
                "aktif_emir": f.order_id,
            }
        return {
            "enabled": self.enabled,
            "furnaces": out,
            "komut_sayisi": len(self.commands),
            "son_komutlar": [c.to_dict() for c in self.commands[-10:]],
        }
