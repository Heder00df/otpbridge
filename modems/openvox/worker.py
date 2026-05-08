"""
Worker para OpenVox GSM Gateway.
Protocolo idêntico ao GoIP — ambos expõem SIP para voz e HTTP para SMS.
A diferença está apenas nos parâmetros do webhook (campo 'channel' em vez de 'line').

Documentação oficial confirma suporte a AT+CCID e API service/simstatus.
Se um modelo específico apresentar problema com ICCID, verificar versão de firmware.
"""
from typing import Callable
from modems.base_worker import BaseModemWorker

class OpenVoxWorker(BaseModemWorker):
    """
    SMS: OpenVox chama POST /openvox/sms com campo 'channel'.
    Voz: canal SIP registrado no Asterisk — mesmo AGI do GoIP.

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

    def deliver_voice(self, wav_path: str):
        if not self.activation_id:
            return
        from otp.whisper_engine import transcribe
        from otp.extractor import extract_from_text
        text = transcribe(wav_path)
        code = extract_from_text(text)
        if code:
            print(f"[OpenVox {self.modem_id}] Voz OTP: {code}")
            self.on_otp(self.activation_id, code, "VOZ")
