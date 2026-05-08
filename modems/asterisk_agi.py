#!/usr/bin/env python3
"""
AGI script compartilhado para E303 (chan_dongle), GoIP e OpenVox.

O dialplan do Asterisk grava a chamada com Record() e chama este script:
  AGI(otpbridge_agi.py,<modem_number>,<wav_path>)

O script repassa o arquivo para o OTPBridge via HTTP (localhost:8000).
Instalar em: /var/lib/asterisk/agi-bin/otpbridge_agi.py
"""
import sys
import json
import urllib.request
import urllib.error

OTPBRIDGE_URL = "http://localhost:8000/internal/voice"


def consume_agi_env():
    """Lê e descarta o cabeçalho de ambiente do protocolo AGI."""
    while True:
        line = sys.stdin.readline()
        if not line or line.strip() == "":
            break


def agi_verbose(msg: str):
    print(f'VERBOSE "{msg}" 1', flush=True)


def main():
    consume_agi_env()

    if len(sys.argv) < 3:
        agi_verbose("otpbridge_agi: argumentos insuficientes (modem_number wav_path)")
        sys.exit(1)

    modem_number = sys.argv[1]
    wav_path = sys.argv[2]

    payload = json.dumps({"modem_number": modem_number, "wav_path": wav_path}).encode()
    req = urllib.request.Request(
        OTPBRIDGE_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            agi_verbose(f"otpbridge_agi: entregue para modem {modem_number} — {resp.status}")
    except urllib.error.HTTPError as e:
        agi_verbose(f"otpbridge_agi: HTTP {e.code} para {modem_number}")
    except Exception as e:
        agi_verbose(f"otpbridge_agi: erro — {e}")


if __name__ == "__main__":
    main()
