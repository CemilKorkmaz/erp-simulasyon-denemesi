"""Alarm ve arıza senaryoları testi."""

from furnace import Furnace, FurnaceStatus


def apply_scenario(furnace: Furnace, scenario: str):
    if scenario == "overheat":
        furnace.state.temperature = furnace.config.max_temp + 20
        furnace.state.status = FurnaceStatus.ALARM
        furnace.state.burner_on = False
        furnace.state.alarm = "Test: Aşırı sıcaklık senaryosu tetiklendi."
    elif scenario == "sensor_failure":
        furnace.state.alarm = "Test: Sensör hatası simülasyonu."
    elif scenario == "burner_failure":
        furnace.state.burner_on = False
        furnace.state.alarm = "Test: Brülör arızası."
    elif scenario == "reset":
        furnace.state.alarm = None
        furnace.state.status = FurnaceStatus.OFF
        furnace.state.burner_on = False
