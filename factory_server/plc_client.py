from __future__ import annotations

import socket
import time
from typing import Optional, Dict, Any, List


def _port_open(ip: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


class PLCClient:
    """Temel PLC arayüzü. Gerçek protokoller bunu extend eder."""

    def connect(self, host: str, port: int) -> bool:
        raise NotImplementedError

    def read_tags(self, tags: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def write_tag(self, address: int, value: Any) -> bool:
        raise NotImplementedError

    def close(self):
        pass


class ModbusTCPClient(PLCClient):
    def __init__(self):
        self.client = None

    def connect(self, host: str, port: int = 502) -> bool:
        try:
            from pymodbus.client import ModbusTcpClient
            self.client = ModbusTcpClient(host, port=port)
            return self.client.connect()
        except Exception:
            return False

    def read_tags(self, tags: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if not self.client:
            return result
        for name, cfg in tags.items():
            try:
                from pymodbus.exceptions import ModbusIOException
                rr = self.client.read_holding_registers(
                    address=int(cfg["address"]), count=1, slave=1
                )
                if rr.isError():
                    result[name] = None
                else:
                    raw = rr.registers[0]
                    result[name] = raw * float(cfg.get("scale", 1.0))
            except Exception:
                result[name] = None
        return result

    def write_tag(self, address: int, value: Any) -> bool:
        try:
            self.client.write_register(address, int(value), slave=1)
            return True
        except Exception:
            return False

    def close(self):
        if self.client:
            self.client.close()


class OPCUAClient(PLCClient):
    def __init__(self):
        self.client = None

    def connect(self, host: str, port: int = 4840) -> bool:
        try:
            from asyncua import Client
            import asyncio

            self.client = Client(f"opc.tcp://{host}:{port}")
            asyncio.get_event_loop().run_until_complete(self.client.connect())
            return True
        except Exception:
            return False

    def read_tags(self, tags: Dict[str, Any]) -> Dict[str, Any]:
        # OPC UA nodeId'ler cfg["node"] ile bilinmelidir; starter'da boş dönülür.
        return {}

    def close(self):
        if self.client:
            import asyncio
            asyncio.get_event_loop().run_until_complete(self.client.disconnect())


class PLCManager:
    def __init__(self, db, scan_subnet: str = "192.168.1"):
        self.db = db
        self.scan_subnet = scan_subnet
        self.client: Optional[PLCClient] = None
        self.connected = False
        self.host: Optional[str] = None
        # PLC'ye göre DEĞİŞMELİ: hangi adreste hangi sensör var
        self.tags: Dict[str, Any] = {
            "sicaklik": {"address": 40001, "type": "holding", "scale": 0.1, "unit": "°C"},
            "durum": {"address": 0, "type": "coil", "scale": 1, "unit": ""},
            "enerji": {"address": 40002, "type": "holding", "scale": 1.0, "unit": "kWh"},
        }

    def scan_network(self, ports: List[int] = None) -> List[Dict[str, str]]:
        if ports is None:
            ports = [502, 4840, 102]  # Modbus, OPC UA, Siemens S7
        found: List[Dict[str, str]] = []
        for i in range(1, 255):
            ip = f"{self.scan_subnet}.{i}"
            for port in ports:
                if _port_open(ip, port):
                    proto = {502: "modbus", 4840: "opcua", 102: "siemens_s7"}.get(port, "bilinmiyor")
                    found.append({"ip": ip, "port": port, "protocol": proto})
        return found

    def connect_plc(self, host: str, port: int = 502, protocol: str = "modbus") -> bool:
        if protocol == "modbus":
            self.client = ModbusTCPClient()
        elif protocol == "opcua":
            self.client = OPCUAClient()
        else:
            return False
        self.host = host
        self.connected = self.client.connect(host, port)
        if self.connected:
            self.db.upsert_machine(
                mid=f"PLC-{host.replace('.', '-')}",
                name=f"PLC {host}",
                plc_ip=host,
                protocol=protocol,
                status="BAĞLı",
            )
        return self.connected

    def poll_once(self) -> Dict[str, Any]:
        if not self.connected or not self.client:
            return {}
        values = self.client.read_tags(self.tags)
        ts = time.time()
        for name, value in values.items():
            if value is not None:
                self.db.add_reading(
                    machine_id=f"PLC-{self.host.replace('.', '-')}",
                    tag_name=name,
                    value=float(value),
                    unit=self.tags[name].get("unit", ""),
                )
        self.db.upsert_machine(
            mid=f"PLC-{self.host.replace('.', '-')}",
            name=f"PLC {self.host}",
            plc_ip=self.host,
            protocol="modbus",
            status="OK",
        )
        return values
