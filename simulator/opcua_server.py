"""OPC UA simülasyon sunucusu.

Fabrika'daki her fırının değişkenlerini (sıcaklık, durum, tüketim, alarm)
OPC UA üzerinden yayımlar. Bu, gerçek bir PLC/SCADA ortamını taklit eder:
ERP tarafı bu sunucuya bir OPC UA istemcisi olarak bağlanıp veri okuyabilir.

Calistirmak icin:  pip install asyncua
"""

from __future__ import annotations

import asyncio
import logging

from asyncua import Server
from simulator.plant import Plant

logger = logging.getLogger("opcua_server")

# Her fırının yayımlayacağı değişkenler ve bunların OPC UA variant türlerini
# belirleyen başlangıç değerleri (browse isimleri).
INIT_VALUES = {
    "anlik_sicaklik": 0.0,
    "hedef_sicaklik": 0.0,
    "maks_sicaklik": 0.0,
    "durum": "",
    "brulor_acik": False,
    "gaz_tuketimi": 0.0,
    "enerji_toplam": 0.0,
    "evrim_suresi": 0.0,
    "alarm": "",
}

VARIABLES = list(INIT_VALUES.keys())


async def run_opcua_server(plant: Plant, host: str = "0.0.0.0",
                           port: int = 4840) -> None:
    server = Server()
    await server.init()
    server.set_endpoint(f"opc.tcp://{host}:{port}/freeopcua/server/")

    uri = "urn:erp-sim:plant"
    idx = await server.register_namespace(uri)

    fabrika = await server.nodes.objects.add_object(idx, "Fabrika")

    furnace_nodes: dict[str, dict] = {}
    for name, furnace in plant.furnaces.items():
        f_node = await fabrika.add_object(idx, name)
        vars_: dict = {}
        for vname in VARIABLES:
            var = await f_node.add_variable(idx, vname, INIT_VALUES[vname])
            await var.set_writable()  # istemci (SCADA/ERP) yazabilse de salt-okunur önerilir
            vars_[vname] = var
        furnace_nodes[name] = vars_

    await server.start()
    logger.info("OPC UA sunucu basladi: opc.tcp://%s:%d/freeopcua/server/", host, port)

    try:
        while True:
            await asyncio.sleep(1.0)
            states = plant.get_states()
            for name, vars_ in furnace_nodes.items():
                s = states[name]
                await vars_["anlik_sicaklik"].set_value(s["temperature"])
                await vars_["hedef_sicaklik"].set_value(s["target_temperature"])
                await vars_["maks_sicaklik"].set_value(s["max_temperature"])
                await vars_["durum"].set_value(s["status"])
                await vars_["brulor_acik"].set_value(s["burner_on"])
                await vars_["gaz_tuketimi"].set_value(s["gas_consumption"])
                await vars_["enerji_toplam"].set_value(s["energy_total"])
                await vars_["evrim_suresi"].set_value(s["cycle_time"])
                await vars_["alarm"].set_value(s["alarm"] or "")
    finally:
        await server.stop()
        logger.info("OPC UA sunucu durduruldu.")
