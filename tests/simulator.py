"""
Simulador de modem — substitui hardware real para testar o fluxo completo.
Simula recebimento de SMS com OTP após 5s da reserva.

Uso: python tests/simulator.py
"""
import json
import threading
import time
import random
import uuid
from pathlib import Path
from typing import Optional, Callable

_SERVICES_PATH = Path(__file__).parent.parent / "services.json"
_ALL_SERVICE_CODES = [s["code"] for s in json.loads(_SERVICES_PATH.read_text())]

SIMULATED_NUMBERS = [
    "5511999990001",
    "5511999990002",
    "5511999990003",
]

class SimulatedModem:
    def __init__(self, modem_id: int, number: str, on_otp: Callable):
        self.modem_id = modem_id
        self.number = number
        self.on_otp = on_otp
        self.activation_id: Optional[str] = None
        self.service: Optional[str] = None
        self.status = "FREE"

    def is_free(self) -> bool:
        return self.status == "FREE"

    def reserve(self, activation_id: str, service: str):
        self.activation_id = activation_id
        self.service = service
        self.status = "BUSY"
        print(f"[Sim Modem {self.modem_id}] reservado — activation={activation_id} service={service}")
        threading.Thread(target=self._deliver_otp, daemon=True).start()

    def release(self, finish_status: int):
        label = "CONCLUÍDO" if finish_status == 3 else "CANCELADO"
        print(f"[Sim Modem {self.modem_id}] {label} (status={finish_status})")
        self.activation_id = None
        self.service = None
        self.status = "FREE"

    def _deliver_otp(self):
        delay = random.randint(3, 8)
        print(f"[Sim Modem {self.modem_id}] SMS chegando em {delay}s...")
        time.sleep(delay)
        if self.activation_id:
            code = str(random.randint(10000, 99999))
            print(f"[Sim Modem {self.modem_id}] SMS recebido → OTP: {code}")
            self.on_otp(self.activation_id, code, "SMS")


class SimulatedModemPool:
    def __init__(self):
        self.modems: dict[int, SimulatedModem] = {}
        self.lock = threading.Lock()

    def start(self):
        for i, number in enumerate(SIMULATED_NUMBERS):
            m = SimulatedModem(
                modem_id=i + 1,
                number=number,
                on_otp=self._on_otp_received,
            )
            self.modems[i + 1] = m
        print(f"[SimPool] {len(self.modems)} modem(s) simulado(s) prontos\n")

    def stop(self):
        pass

    def get_services(self) -> dict:
        with self.lock:
            free = sum(1 for m in self.modems.values() if m.is_free())
        return {
            "status": "success",
            "services": {code: free for code in _ALL_SERVICE_CODES},
        }

    def reserve_modem(self, service: str, country=None):
        with self.lock:
            for m in self.modems.values():
                if m.is_free():
                    activation_id = str(uuid.uuid4())
                    m.reserve(activation_id, service)
                    return {"activation_id": activation_id, "number": m.number}
        return None

    def finish_activation(self, activation_id: str, status: int):
        with self.lock:
            for m in self.modems.values():
                if m.activation_id == activation_id:
                    m.release(status)
                    return

    def _on_otp_received(self, activation_id: str, code: str, otp_type: str):
        from herosms.client import push_sms
        push_sms(activation_id, code, otp_type)
