import subprocess
import threading
import time
from typing import Callable
from modems.base_worker import BaseModemWorker
from otp.extractor import extract_from_sms


class E303Worker(BaseModemWorker):
    """
    Worker para Huawei E303 via chan_dongle + Asterisk.
    SMS: recebido via webhook POST /e303/sms (ver modems/e303/webhook.py)
    Voz: chan_dongle registra dongle no Asterisk — ver modems/asterisk_agi.py

    Config por dongle:
      dongle_name = nome do dispositivo no chan_dongle (ex: dongle0)
      number      = número do SIM
    """

    def __init__(self, modem_id: int, dongle_name: str, number: str, on_otp: Callable):
        self.dongle_name = dongle_name
        self._rssi = 0
        self._rssi_lock = threading.Lock()
        super().__init__(modem_id=modem_id, number=number, on_otp=on_otp)
        # poll rssi desabilitado temporariamente
        # threading.Thread(target=self._poll_rssi, daemon=True).start()

    def start(self):
        import db.repository as repo
        self.status = "FREE"
        repo.upsert_modem(self.modem_id, self.number, "e303",
                          porta_usb=self.dongle_name, suporta_voz=True)
        print(f"[E303 {self.modem_id}] online — {self.dongle_name} — {self.number}")

    def stop(self):
        self.status = "OFFLINE"

    def rssi(self) -> int:
        with self._rssi_lock:
            return self._rssi

    def set_rssi(self, value: int):
        with self._rssi_lock:
            self._rssi = value

    def deliver_sms(self, text: str):
        """Chamado pelo E303Webhook quando SMS chega neste dongle."""
        import db.repository as repo
        code = extract_from_sms(text)
        repo.log_sms(self.modem_id, self.activation_id, text, code)
        if not self.activation_id or not code:
            return
        print(f"[E303 {self.modem_id}] SMS OTP: {code}")
        repo.atualizar_ativacao(self.activation_id, "SMS_RECEBIDO", "SMS", code)
        self.on_otp(self.activation_id, code, "SMS")

    def deliver_voice(self, wav_path: str):
        """Chamado pelo AGI do Asterisk após gravar a chamada entrante."""
        if not self.activation_id:
            return
        import db.repository as repo
        from otp.whisper_engine import transcribe
        from otp.extractor import extract_from_text
        text = transcribe(wav_path)
        code = extract_from_text(text)
        repo.log_voz(self.modem_id, self.activation_id, text, code, duracao=0)
        if code:
            print(f"[E303 {self.modem_id}] Voz OTP: {code}")
            self.on_otp(self.activation_id, code, "VOZ")
