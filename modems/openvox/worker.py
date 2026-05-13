from typing import Callable
from modems.base_worker import BaseModemWorker

class OpenVoxWorker(BaseModemWorker):
    """
    Worker para OpenVox GSM Gateway.
    SMS: OpenVox chama POST /openvox/sms com campo 'channel'.

    Config por canal:
      ip      = IP do OpenVox na LAN
      channel = número do canal/SIM (1..N)
      number  = número do SIM
    """

    def __init__(self, modem_id: int, ip: str, channel: int, number: str, on_otp: Callable):
        self.ip = ip
        self.channel = channel
        super().__init__(modem_id=modem_id, number=number, on_otp=on_otp)

    def start(self):
        self.status = "FREE"
        print(f"[OpenVox {self.modem_id}] online — {self.ip} canal {self.channel} — {self.number}")

    def stop(self):
        self.status = "OFFLINE"

    def deliver_sms(self, text: str):
        if not self.activation_id:
            return
        from otp.extractor import extract_from_sms
        code = extract_from_sms(text)
        if code:
            print(f"[OpenVox {self.modem_id}] SMS OTP: {code}")
            self.on_otp(self.activation_id, code, "SMS")
