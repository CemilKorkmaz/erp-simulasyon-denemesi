"""Sanal fabrika: birden fazla fırını ve üretim emirlerini yönetir."""

from __future__ import annotations

import time
from typing import Optional

from simulator.furnace import Furnace, FurnaceParams, FurnaceStatus


class Plant:
    """Tüm sanal ekipmanları ve üretim emirini barındıran fabrika modeli."""

    def __init__(self) -> None:
        self.furnaces: dict[str, Furnace] = {}
        self.orders: dict[str, dict] = {}
        self._order_counter = 0

    # ------------------------------------------------------------------ ekipman

    def add_furnace(self, params: FurnaceParams) -> None:
        self.furnaces[params.name] = Furnace(params)

    def get_states(self) -> dict[str, dict]:
        return {name: f.to_dict() for name, f in self.furnaces.items()}

    def get_furnace(self, name: str) -> Optional[Furnace]:
        return self.furnaces.get(name)

    def free_furnaces(self) -> list[str]:
        """Emri atanmamış ve alarmda olmayan fırınlar."""
        return [
            name for name, f in self.furnaces.items()
            if f.order_id is None and f.state.status != FurnaceStatus.ALARM
        ]

    # --------------------------------------------------------------- emirler

    def create_order(self, product: str, furnace: str, target_temp: float,
                     duration_min: float) -> str:
        today = time.strftime("%Y%m%d")
        self._order_counter += 1
        order_id = f"WO-{today}-{self._order_counter:04d}"
        now = time.time()
        self.orders[order_id] = {
            "id": order_id,
            "product": product,
            "furnace": furnace,
            "target_temp": target_temp,
            "duration_min": duration_min,
            "state": "CREATED",   # CREATED / RUNNING / COMPLETED / CANCELLED
            "created_at": now,
            "started_at": None,
            "finished_at": None,
        }
        return order_id

    def start_order(self, order_id: str, furnace: str) -> bool:
        order = self.orders.get(order_id)
        furnace_obj = self.furnaces.get(furnace)
        if not order or not furnace_obj:
            return False
        if order["state"] != "CREATED":
            return False
        if furnace_obj.order_id is not None:
            return False  # fırın zaten meşgul
        now = time.time()
        order["state"] = "RUNNING"
        order["started_at"] = now
        order["furnace"] = furnace
        furnace_obj.start_order(
            order_id=order_id,
            product=order["product"],
            target_temp=order["target_temp"],
            duration_min=order["duration_min"],
            now=now,
        )
        return True

    def get_orders(self) -> list[dict]:
        # Sıralı döndür: en yeni önce.
        return sorted(self.orders.values(), key=lambda o: o["created_at"],
                      reverse=True)

    def get_order(self, order_id: str) -> Optional[dict]:
        return self.orders.get(order_id)

    # ------------------------------------------------------------------ simülasyon

    def update(self, dt: float) -> list[dict]:
        """Tüm fırınları bir adım ilerletir; emir durumlarını senkronize eder."""
        events: list[dict] = []
        for furnace in self.furnaces.values():
            for event in furnace.update(dt):
                if event["type"] == "order_completed":
                    summary = event["summary"]
                    order = self.orders.get(summary["order_id"])
                    if order:
                        order["state"] = "COMPLETED"
                        order["finished_at"] = time.time()
                        order["energy_total_m3"] = summary["energy_total_m3"]
                        order["cycle_time_s"] = summary["cycle_time_s"]
                events.append(event)
        return events
