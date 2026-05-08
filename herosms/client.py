import requests
from config import HEROSMS_API_URL, HEROSMS_KEY

def push_sms(activation_id: str, code: str, otp_type: str = "SMS"):
    payload = {
        "key": HEROSMS_KEY,
        "activationId": activation_id,
        "text": f"OTPBridge code: {code}",
        "code": code,
    }
    try:
        r = requests.post(HEROSMS_API_URL, json=payload, timeout=10)
        r.raise_for_status()
        print(f"[HeroSMS] PUSH_SMS ok — activation={activation_id} code={code} type={otp_type}")
    except Exception as e:
        print(f"[HeroSMS] PUSH_SMS erro — {e}")
