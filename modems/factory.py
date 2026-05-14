"""
Lê a configuração e instancia os workers corretos.

config.py define HARDWARE_TYPE = "e303" | "goip" | "openvox"
e uma lista DEVICES com os parâmetros de cada canal/modem.

Exemplos de DEVICES:

  # E303 — detectado automaticamente via USB
  HARDWARE_TYPE = "e303"
  DEVICES = []  # vazio = auto-detectar com modems/e303/detector.py

  # GoIP com 8 canais
  HARDWARE_TYPE = "goip"
  DEVICES = [
    {"ip": "192.168.1.200", "line": 1, "number": "5511999990001"},
    {"ip": "192.168.1.200", "line": 2, "number": "5511999990002"},
    ...
  ]

  # OpenVox com 4 canais
  HARDWARE_TYPE = "openvox"
  DEVICES = [
    {"ip": "192.168.1.201", "channel": 1, "number": "5511999990010"},
    ...
  ]
"""
from typing import Callable
from modems.base_worker import BaseModemWorker

def create_workers(hardware_type: str, devices: list, on_otp: Callable) -> list[BaseModemWorker]:
    workers = []

    if hardware_type == "e303":
        from modems.e303.detector import detect_modems
        from modems.e303.worker import E303Worker
        found = detect_modems() if not devices else [
            (d["mm_index"], d.get("number", "unknown"), 0) for d in devices
        ]
        for mm_index, number, db_id in found:
            if not db_id:
                print(f"[Factory] MM:{mm_index} sem db_id — ignorado")
                continue
            workers.append(E303Worker(
                modem_id=db_id,
                mm_index=mm_index,
                number=number,
                on_otp=on_otp,
            ))

    elif hardware_type == "goip":
        from modems.goip.worker import GoIPWorker
        for i, d in enumerate(devices):
            workers.append(GoIPWorker(
                modem_id=i + 1,
                ip=d["ip"],
                line=d["line"],
                number=d["number"],
                on_otp=on_otp,
            ))

    elif hardware_type == "openvox":
        from modems.openvox.worker import OpenVoxWorker
        for i, d in enumerate(devices):
            workers.append(OpenVoxWorker(
                modem_id=i + 1,
                ip=d["ip"],
                channel=d["channel"],
                number=d["number"],
                on_otp=on_otp,
            ))

    else:
        raise ValueError(f"HARDWARE_TYPE desconhecido: {hardware_type}")

    return workers
