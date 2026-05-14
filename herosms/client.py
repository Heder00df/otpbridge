import threading
import time
import requests
from config import HEROSMS_KEY

_BASE_URL  = "https://api.partnersservices.net"
_USER_AGENT = "OTPBridge/1.0"
_HEADERS = {
    "User-Agent":       _USER_AGENT,
    "Accept-Encoding":  "gzip",
    "Content-Type":     "application/json",
}


def push_sms(sms_id: int, phone: str, phone_from: str, text: str):
    """
    Envia SMS recebido para a HeroSMS.
    Retentar a cada 10s até receber SUCCESS (conforme protocolo).
    Executa em background para não bloquear o worker.
    """
    payload = {
        "action":    "PUSH_SMS",
        "key":       HEROSMS_KEY,
        "smsId":     int(sms_id),
        "phone":     int(phone),
        "phoneFrom": str(phone_from),
        "text":      str(text),
    }
    threading.Thread(
        target=_push_with_retry,
        args=(f"{_BASE_URL}/agent/api/sms", payload, f"smsId={sms_id}"),
        daemon=True,
    ).start()


def _push_with_retry(url: str, payload: dict, label: str):
    """Retentar indefinidamente a cada 10s até receber SUCCESS."""
    attempt = 0
    while True:
        attempt += 1
        try:
            r = requests.post(url, json=payload, headers=_HEADERS, timeout=15)
            r.raise_for_status()
            data = r.json()
            if data.get("status") == "SUCCESS":
                print(f"[HeroSMS] {label} enviado OK (tentativa {attempt})")
                return
            print(f"[HeroSMS] {label} resposta não-SUCCESS: {data} — retentando em 10s")
        except Exception as e:
            print(f"[HeroSMS] {label} erro tentativa {attempt}: {e} — retentando em 10s")
        time.sleep(10)


def ping() -> bool:
    try:
        r = requests.get(f"{_BASE_URL}/agent/api/ping",
                         headers=_HEADERS, timeout=5)
        return r.json().get("status") == "SUCCESS"
    except Exception:
        return False
