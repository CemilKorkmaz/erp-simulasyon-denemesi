from dataclasses import dataclass
from typing import List


@dataclass
class FurnaceConfig:
    name: str
    furnace_type: str  # ERITME, HOMOJENIZASYON, BIYET_ISITMA
    ambient_temp: float = 25.0
    target_temp: float = 750.0
    max_temp: float = 850.0
    heat_rate: float = 2.0      # °C/sn maksimum ısıtma
    cool_rate: float = 0.03     # Soğuma katsayısı
    hold_band: float = 5.0      # Termostat bandı (°C)
    gas_consumption_full: float = 120.0  # m³/saat brülör açıkken


FACTORY_FURNACES: List[FurnaceConfig] = [
    FurnaceConfig(
        name="Alüminyum Ergitme Fırını",
        furnace_type="ERITME",
        target_temp=750.0,
        max_temp=850.0,
        heat_rate=2.5,
        cool_rate=0.03,
        gas_consumption_full=120.0,
    ),
    FurnaceConfig(
        name="Homojenizasyon Fırını",
        furnace_type="HOMOJENIZASYON",
        target_temp=560.0,
        max_temp=620.0,
        heat_rate=1.2,
        cool_rate=0.03,
        gas_consumption_full=80.0,
    ),
    FurnaceConfig(
        name="Biyet Isıtma Fırını",
        furnace_type="BIYET_ISITMA",
        target_temp=480.0,
        max_temp=540.0,
        heat_rate=1.8,
        cool_rate=0.03,
        gas_consumption_full=60.0,
    ),
]

OPCUA_ENDPOINT = "opc.tcp://0.0.0.0:4840/freeopcua/server/"
ERP_API_PORT = 8000
DB_PATH = "factory_sim.db"
