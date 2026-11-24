"""SQLite tabanlı hafif veritabanı katmanı.

Gerçek fabrika geçişinde burayı PostgreSQL'e (SQLAlchemy modelleriyle)
tek seferde geçirebilirsiniz. Simülasyon için dosya tabanlı SQLite
yeterlidir ve hiçbir sunucu kurulumu gerektirmez.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from typing import Optional


class Database:
    def __init__(self, path: str = "erp_sim.db"):
        self.path = path
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init()

    def init(self) -> None:
        with self.lock:
            self.conn.executescript(
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
                CREATE INDEX IF NOT EXISTS idx_readings_furnace_ts
                    ON readings(furnace, ts);

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
            self.conn.commit()

    # --------------------------------------------------------------- okunur veri

    def add_reading(self, furnace: str, temperature: float, target_temperature: float,
                    status: str, burner_on: bool, gas_consumption: float,
                    energy_total: float, cycle_time: float,
                    alarm: Optional[str]) -> None:
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO readings
                    (furnace, temperature, target_temperature, status, burner_on,
                     gas_consumption, energy_total, cycle_time, alarm, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    furnace, temperature, target_temperature, status,
                    int(burner_on), gas_consumption, energy_total, cycle_time,
                    alarm, time.time(),
                ),
            )
            self.conn.commit()

    def get_readings(self, furnace: str, limit: int = 200) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                """
                SELECT * FROM readings
                WHERE furnace = ?
                ORDER BY ts DESC
                LIMIT ?
                """,
                (furnace, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_latest(self, furnace: str) -> Optional[dict]:
        with self.lock:
            row = self.conn.execute(
                """
                SELECT * FROM readings
                WHERE furnace = ?
                ORDER BY ts DESC
                LIMIT 1
                """,
                (furnace,),
            ).fetchone()
        return dict(row) if row else None

    # --------------------------------------------------------------- emirler

    def add_order(self, order_id: str, product: str, furnace: str, target_temp: float,
                  duration_min: float, state: str, created_at: float) -> None:
        with self.lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO production_orders
                    (id, product, furnace, target_temp, duration_min, state,
                     created_at, started_at, finished_at, energy_total_m3, cycle_time_s)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)
                """,
                (order_id, product, furnace, target_temp, duration_min,
                 state, created_at),
            )
            self.conn.commit()

    def get_orders(self) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                """
                SELECT * FROM production_orders
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def close_stale_orders(self) -> int:
        """Önceki oturumdan RUNNING kalan emirleri kapatır.

        Sunucu kapanınca fırın durumu bellekte kayboluyor; DB'de RUNNING
        kalan emir 'hayalet emir' olarak kalıyordu ve ERP panelinde hiç
        bitmeyen bir iş gibi görünüyordu. Açılışta bunları INTERRUPTED
        olarak işaretliyoruz (CANCELLED'dan farkı: kaza eseri kesildi).
        """
        with self.lock:
            cur = self.conn.execute(
                """
                UPDATE production_orders
                   SET state = 'INTERRUPTED', finished_at = ?
                 WHERE state IN ('RUNNING', 'CREATED')
                """,
                (time.time(),),
            )
            self.conn.commit()
            return cur.rowcount

    def update_order(self, order_id: str, **fields) -> None:
        """Satır yoksa oluşturur (upsert).

        PLC üzerinden başlatılan emirler (ERP -> /api/plc/start) doğrudan
        fırına yazıldığı için production_orders'ta satırı olmayabilir. Bu
        durumda düz UPDATE hiçbir şey yapmıyor ve tamamlanan emir veritabanına
        hiç işlenmiyordu.
        """
        if not fields:
            return
        if self.conn.execute(
            "SELECT 1 FROM production_orders WHERE id = ?", (order_id,)
        ).fetchone() is None:
            self._insert_order_row(order_id, fields)
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self.lock:
            self.conn.execute(
                f"UPDATE production_orders SET {cols} WHERE id = ?",
                (*fields.values(), order_id),
            )
            self.conn.commit()

    def _insert_order_row(self, order_id: str, fields: dict) -> None:
        """Bilinmeyen emri, verilen alanlar + makul varsayılanlarla ekler."""
        now = time.time()
        vals = {
            "id": order_id,
            "product": fields.get("product") or "(PLC emri)",
            "furnace": fields.get("furnace") or "(bilinmiyor)",
            "target_temp": float(fields.get("target_temp") or 0.0),
            "duration_min": float(fields.get("duration_min") or 0.0),
            "state": fields.get("state") or "RUNNING",
            "created_at": float(fields.get("created_at") or now),
        }
        with self.lock:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO production_orders
                    (id, product, furnace, target_temp, duration_min, state,
                     created_at, started_at, finished_at, energy_total_m3, cycle_time_s)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)
                """,
                (vals["id"], vals["product"], vals["furnace"],
                 vals["target_temp"], vals["duration_min"], vals["state"],
                 vals["created_at"]),
            )
            self.conn.commit()
