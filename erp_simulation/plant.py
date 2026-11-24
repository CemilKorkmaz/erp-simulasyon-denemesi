"""Sanal fabrika: birden fazla fırın ve üretim emri yönetimi."""

from __future__ import annotations

import time
from typing import Optional

from furnace import Furnace, FurnaceStatus
from config import FACTORY_FURNACES


class Plant:
    def __init__(self, configs=None):
        self.furnaces = {}
        configs = configs or FACTORY_FURNACES
        for cfg in configs:
            self.furnaces[cfg.name] = Furnace(cfg)
        self.orders = {}
        self._order_counter = 0

    def get_states(self):
        return {name: f.to_dict() for name, f in self.furnaces.items()}

    def get_furnace(self, name: str) -> Optional[Furnace]:
        return self.furnaces.get(name)

    def get_order(self, order_id: str) -> Optional[dict]:
        return self.orders.get(order_id)

    def create_order(self, product: str, furnace: str, target_temp: float,
                     duration_min: float) -> str:
        self._order_counter += 1
        order_id = f"WO-{time.strftime('%Y%m%d')}-{self._order_counter:04d}"
        self.orders[order_id] = {
            "id": order_id,
            "product": product,
            "furnace": furnace,
            "target_temp": target_temp,
            "duration_min": duration_min,
            "state": "CREATED",
            "created_at": time.time(),
            "started_at": None,
            "finished_at": None,
        }
        return order_id

    def start_order(self, order_id: str, furnace: str) -> bool:
        order = self.orders.get(order_id)
        f = self.furnaces.get(furnace)
        if not order or not f:
            return False
        if order["state"] != "CREATED":
            return False
        if f.state.order_id is not None:
            return False
        now = time.time()
        order["state"] = "RUNNING"
        order["started_at"] = now
        f.start_order(
            order_id=order_id,
            product=order["product"],
            target_temp=order["target_temp"],
            duration_min=order["duration_min"],
            now=now,
        )
        return True

    def get_orders(self):
        return sorted(self.orders.values(), key=lambda o: o["created_at"],
                      reverse=True)

    def update(self, dt: float) -> list[dict]:
        events = []
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
