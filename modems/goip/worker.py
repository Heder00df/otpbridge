from typing import Callable
from modems.base_worker import BaseModemWorker

class GoIPWorker(BaseModemWorker):
    """
    Worker para GoIP (DBL Technology).
    SMS: recebido via webhook POST /goip/sms

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

