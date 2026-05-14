import re
import subprocess
import threading
import time
from typing import Callable

from modems.base_worker import BaseModemWorker
from otp.extractor import extract_from_sms

_POLL_INTERVAL = 2.0
_MIN_SIGNAL = 20  # % mínimo para aceitar ativações


class E303Worker(BaseModemWorker):
    def __init__(self, modem_id: int, mm_index: int, number: str, on_otp: Callable):
        self.mm_index = mm_index
        self.port_at = None
        self.port_audio = None
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        super().__init__(modem_id=modem_id, number=number, on_otp=on_otp)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self.status = "OFFLINE"

    # ── helpers mmcli ────────────────────────────────────────

    def _mmcli(self, *args) -> str:
        r = subprocess.run(["mmcli"] + list(args), capture_output=True, text=True)
        return r.stdout

    def _modem_info(self) -> dict:
        out = self._mmcli("-m", str(self.mm_index))
        info = {"state": "unknown", "signal": 0, "signal_fresh": False}
        for line in out.splitlines():
            if "|" not in line:
                continue
            if "state:" in line and "power state" not in line and "packet service" not in line:
                info["state"] = line.split("state:")[-1].strip()
            elif "signal quality:" in line:
                m = re.search(r"(\d+)%", line)
                if m:
                    info["signal"] = int(m.group(1))
                info["signal_fresh"] = "recent" in line
        return info

    def _list_sms(self) -> list[str]:
        out = self._mmcli("-m", str(self.mm_index), "--messaging-list-sms")
        return [l.split()[0] for l in out.splitlines() if "/SMS/" in l]

    def _read_sms(self, path: str) -> dict:
        out = self._mmcli("--sms", path)
        number, text = "", ""
        for line in out.splitlines():
            if "number:" in line:
                number = line.split("number:")[-1].strip()
            elif "text:" in line:
                text = line.split("text:", 1)[-1].strip()
        return {"number": number, "text": text, "path": path}

    def _delete_sms(self, path: str):
        subprocess.run(["mmcli", "--sms", path, "--delete"],
                       capture_output=True)

    # ── main thread ──────────────────────────────────────────

    def _run(self):
        import db.repository as repo

        repo.upsert_modem(self.modem_id, self.number, "e303",
                          None, None, suporta_voz=False)

        # Ativa medição de sinal periódica (a cada 5s)
        subprocess.run(["mmcli", "-m", str(self.mm_index), "--signal-setup=5"],
                       capture_output=True)

        known_sms: set[str] = set(self._list_sms())

        while not self._stop_event.is_set():
            try:
                info = self._modem_info()
                st = info["state"]
                signal = info["signal"]

                # Aceita sinal cached != 0 enquanto não tiver leitura recente
                signal_ok = signal >= _MIN_SIGNAL or (not info["signal_fresh"] and signal > 0)
                is_ready = st in ("registered", "connected") and signal_ok

                if is_ready:
                    if self.status == "OFFLINE":
                        self.status = "FREE"
                        print(f"[E303 {self.modem_id}] pronto — MM:{self.mm_index} — {self.number} — sinal {signal}%")
                else:
                    if self.status == "FREE":
                        self.status = "OFFLINE"
                        print(f"[E303 {self.modem_id}] indisponível — {st} sinal={signal}% — MM:{self.mm_index}")

                # Processa SMS independente do sinal (pode ter chegado antes de cair)
                if st in ("registered", "connected"):
                    current = set(self._list_sms())
                    new_paths = current - known_sms
                    for path in new_paths:
                        sms = self._read_sms(path)
                        self._handle_sms(sms)
                        self._delete_sms(path)
                    known_sms = current

            except Exception as e:
                print(f"[E303 {self.modem_id}] poll erro: {e}")
            time.sleep(_POLL_INTERVAL)

    # ── SMS ──────────────────────────────────────────────────

    def _handle_sms(self, sms: dict):
        import db.repository as repo
        import re
        text = sms["text"]
        phone_from = sms.get("number", "unknown")

        # Mensagens de discovery não vão para HeroSMS nem para o log normal
        from modems.e303.sms_discovery import record_sms
        if re.search(r"ID:MM\d+", text):
            record_sms(self.mm_index, phone_from, text)
            return

        code = extract_from_sms(text)
        sms_id = repo.log_sms(self.modem_id, self.activation_id, text, code)
        print(f"[E303 {self.modem_id}] SMS de={phone_from} texto='{text}' codigo={code}")

        if not self.activation_id:
            return
        repo.atualizar_ativacao(self.activation_id, "SMS_RECEBIDO", "SMS", code)
        from herosms.client import push_sms
        push_sms(sms_id=sms_id, phone=self.number, phone_from=phone_from, text=text)
