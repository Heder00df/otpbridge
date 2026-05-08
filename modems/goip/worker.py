import threading
import requests
from typing import Callable
from modems.base_worker import BaseModemWorker
from otp.extractor import extract_from_sms

class GoIPWorker(BaseModemWorker):
    """
    Worker para GoIP (DBL Technology).
    SMS: recebido via webhook POST /goip/sms (ver api/goip_webhook.py)
         ou polling na interface web do GoIP.
    Voz: GoIP registra canal SIP no Asterisk — ver modems/goip/asterisk_agi.py

    Config por canal:
      ip     = IP do dispositivo GoIP na LAN (ex: 192.168.1.200)
      line   = número da linha/SIM (1..N)
      number = número do SIM nessa linha
    """

    def __init__(self, modem_id: int, ip: str, line: int, number: str, on_otp: Callable):
        self.ip = ip
        self.line = line
        super().__init__(modem_id=modem_id, number=number, on_otp=on_otp)

    def start(self):
        self.status = "FREE"
        print(f"[GoIP {self.modem_id}] online — {self.ip} linha {self.line} — {self.number}")

    def stop(self):
        self.status = "OFFLINE"

    def deliver_sms(self, text: str):
        """Chamado pelo GoIPWebhook quando SMS chega nesta linha."""
        if not self.activation_id:
            return
        from otp.extractor import extract_from_sms
        code = extract_from_sms(text)
        if code:
            print(f"[GoIP {self.modem_id}] SMS OTP: {code}")
            self.on_otp(self.activation_id, code, "SMS")

    def deliver_voice(self, wav_path: str):
        """Chamado pelo AGI do Asterisk após gravar e converter a chamada."""
        if not self.activation_id:
            return
        import db.repository as repo
        from otp.whisper_engine import transcribe
        from otp.extractor import extract_from_text
        text = transcribe(wav_path)
        code = extract_from_text(text)
        repo.log_voz(self.modem_id, self.activation_id, text, code, duracao=0)
        if code:
            print(f"[GoIP {self.modem_id}] Voz OTP: {code}")
            self.on_otp(self.activation_id, code, "VOZ")
