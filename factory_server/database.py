import sqlite3
import time
from typing import Optional


class FactoryDB:
    def __init__(self, path: str = "factory_erp.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init()

    def init(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS machines (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                plc_ip TEXT,
                protocol TEXT,
                status TEXT DEFAULT 'BILINMIYOR',
                last_seen REAL
            );
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                tag_name TEXT NOT NULL,
                value REAL,
                unit TEXT,
                ts REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_readings_machine_ts
                ON readings(machine_id, ts);
            """
        )
        self.conn.commit()

    def upsert_machine(self, mid: str, name: str, plc_ip: str, protocol: str, status: str):
        self.conn.execute(
            """
            INSERT INTO machines (id, name, plc_ip, protocol, status, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                plc_ip=excluded.plc_ip,
                protocol=excluded.protocol,
                status=excluded.status,
                last_seen=excluded.last_seen
            """,
            (mid, name, plc_ip, protocol, status, time.time()),
        )
        self.conn.commit()

    def add_reading(self, machine_id: str, tag_name: str, value: float, unit: str):
        self.conn.execute(
            "INSERT INTO readings (machine_id, tag_name, value, unit, ts) VALUES (?, ?, ?, ?, ?)",
            (machine_id, tag_name, value, unit, time.time()),
        )
        self.conn.commit()

    def get_machines(self):
        rows = self.conn.execute("SELECT * FROM machines ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def get_readings(self, machine_id: str, limit: int = 100):
        rows = self.conn.execute(
            "SELECT * FROM readings WHERE machine_id=? ORDER BY ts DESC LIMIT ?",
            (machine_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_latest_reading(self, machine_id: str, tag_name: str):
        row = self.conn.execute(
            "SELECT * FROM readings WHERE machine_id=? AND tag_name=? ORDER BY ts DESC LIMIT 1",
            (machine_id, tag_name),
        ).fetchone()
        return dict(row) if row else None
