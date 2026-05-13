import requests
from config import HEROSMS_KEY

_BASE_URL = "https://api.partnersservices.net"


def push_sms(sms_id: int, phone: str, phone_from: str, text: str):
    """
    Envia SMS recebido para a HeroSMS.
    - phone      : número do nosso modem (receptor) — inteiro
    - phone_from : remetente do SMS (ex: "Telegram", "TIM")
    - text       : texto completo do SMS
    - sms_id     : ID do registro na nossa sms_log
    """
    payload = {
        "key":       HEROSMS_KEY,
        "phone":     int(phone),
        "phoneFrom": phone_from,
        "smsId":     str(sms_id),
        "text":      text,
    }
    try:
        r = requests.post(f"{_BASE_URL}/agent/api/sms", json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "SUCCESS":
            print(f"[HeroSMS] SMS enviado — smsId={sms_id} phone={phone}")
        else:
            print(f"[HeroSMS] ERRO — {data}")
    except Exception as e:
        print(f"[HeroSMS] push_sms erro — {e}")


def ping() -> bool:
    try:
        r = requests.get(f"{_BASE_URL}/agent/api/ping", timeout=5)
        return r.json().get("status") == "SUCCESS"
    except Exception:
        return False
