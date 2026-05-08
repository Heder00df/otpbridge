#!/usr/bin/env python3
"""
AGI script para SMS entrante via chan_dongle.
Chamado pelo dialplan quando SMS chega em qualquer dongle.

Dialplan (extensions.conf):
  exten => sms,1,AGI(otpbridge_sms_agi.py,${DONGLENAME},${CALLERID(num)},${SMS_BODY})

Instalar em: /usr/share/asterisk/agi-bin/otpbridge_sms_agi.py
"""
import sys
import json
import urllib.request
import urllib.error

OTPBRIDGE_URL = "http://localhost:8000/e303/sms"


def consume_agi_env():
    while True:
        line = sys.stdin.readline()
        if not line or line.strip() == "":
            break


def agi_verbose(msg: str):
    print(f'VERBOSE "{msg}" 1', flush=True)


def main():
    consume_agi_env()

    if len(sys.argv) < 4:
        agi_verbose("otpbridge_sms_agi: argumentos insuficientes (dongle_name from_number text)")
        sys.exit(1)

    dongle_name = sys.argv[1]
    from_number = sys.argv[2]
    text        = sys.argv[3]

    payload = json.dumps({
        "dongle_name": dongle_name,
        "from_number": from_number,
        "text": text,
    }).encode()

    req = urllib.request.Request(
        OTPBRIDGE_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            agi_verbose(f"otpbridge_sms_agi: entregue dongle={dongle_name} — {resp.status}")
    except urllib.error.HTTPError as e:
        agi_verbose(f"otpbridge_sms_agi: HTTP {e.code} dongle={dongle_name}")
    except Exception as e:
        agi_verbose(f"otpbridge_sms_agi: erro — {e}")


if __name__ == "__main__":
    main()
