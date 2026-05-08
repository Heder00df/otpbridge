import json
import threading
import uuid
from pathlib import Path
from typing import Optional
from modems.base_worker import BaseModemWorker
from modems.factory import create_workers
from config import HARDWARE_TYPE, DEVICES
import db.repository as repo

_SERVICES_PATH = Path(__file__).parent.parent / "services.json"
_ALL_SERVICE_CODES = [s["code"] for s in json.loads(_SERVICES_PATH.read_text())]

_pool_instance: Optional["ModemPool"] = None

def get_pool() -> "ModemPool":
    return _pool_instance

class ModemPool:
    def __init__(self):
        global _pool_instance
        self.modems: dict[int, BaseModemWorker] = {}
        self.lock = threading.Lock()
        _pool_instance = self

    def start(self):
        workers = create_workers(HARDWARE_TYPE, DEVICES, self._on_otp_received)
        for w in workers:
            w.start()
            self.modems[w.modem_id] = w
            repo.upsert_modem(
                modem_id=w.modem_id,
                numero=w.number,
                hardware=HARDWARE_TYPE,
                porta_usb=getattr(w, "port_at", None) or (
                    f"MM:{w.mm_index}" if hasattr(w, "mm_index") else None
                ),
                porta_audio=getattr(w, "port_audio", None),
                suporta_voz=False,
            )
            repo.log_evento("MODEM_ONLINE", modem_id=w.modem_id)
        print(f"[Pool] {len(self.modems)} modem(s) iniciado(s) — hardware: {HARDWARE_TYPE}")

    def stop(self):
        for w in self.modems.values():
            w.stop()
            repo.log_evento("MODEM_OFFLINE", modem_id=w.modem_id)

    def get_services(self) -> dict:
        with self.lock:
            free = sum(1 for m in self.modems.values() if m.is_free())
        return {
            "status": "success",
            "services": {code: free for code in _ALL_SERVICE_CODES},
        }

    def reserve_modem(self, service: str, country: Optional[str]) -> Optional[dict]:
        with self.lock:
            for w in self.modems.values():
                if w.is_free() and not w.number.startswith("unknown"):
                    activation_id = str(uuid.uuid4())
                    w.reserve(activation_id, service)
                    repo.set_modem_status(w.modem_id, "BUSY", activation_id)
                    repo.criar_ativacao(activation_id, w.modem_id, service,
                                        w.number, pais=country)
                    repo.log_evento("ATIVACAO_CRIADA", w.modem_id, activation_id,
                                    f"servico={service} pais={country}")
                    return {"activation_id": activation_id, "number": w.number}
        return None

    def finish_activation(self, activation_id: str, status: int):
        status_label = "CONCLUIDO" if status == 3 else "CANCELADO"
        with self.lock:
            for w in self.modems.values():
                if w.activation_id == activation_id:
                    w.release(status)
                    repo.set_modem_status(w.modem_id, "FREE")
                    repo.atualizar_ativacao(activation_id, status_label)
                    repo.log_evento(status_label, w.modem_id, activation_id)
                    return

    def find_by_line(self, hardware: str, line: int) -> Optional[BaseModemWorker]:
        with self.lock:
            for w in self.modems.values():
                if hardware == "goip" and hasattr(w, "line") and w.line == line:
                    return w
                if hardware == "openvox" and hasattr(w, "channel") and w.channel == line:
                    return w
        return None

    def _on_otp_received(self, activation_id: str, code: str, otp_type: str):
        with self.lock:
            for w in self.modems.values():
                if w.activation_id == activation_id:
                    repo.atualizar_ativacao(activation_id, "PUSH_ENVIADO",
                                            tipo_otp=otp_type, codigo=code)
                    repo.log_evento("PUSH_OK", w.modem_id, activation_id,
                                    f"code={code} tipo={otp_type}")
                    break
        from herosms.client import push_sms
        push_sms(activation_id, code, otp_type)
