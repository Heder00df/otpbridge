#!/usr/bin/env python3
"""Mapeia cada porta USB para o dongle Asterisk e o número real.

Mostra:
  - porta /dev/ttyUSB* usada pelo dongle
  - nome do dongle (dongleX)
  - número atual exibido pelo Asterisk
  - estado do dongle
  - número salvo em .env para esse dongle, se houver

Uso:
  python3 tools/map_usb_numbers.py
"""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DONGLE_CONF = ROOT / "asterisk" / "dongle.conf"
ENV_FILE = ROOT / ".env"


def run_cmd(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout or ""


def parse_dongle_devices(output):
    dongles = {}
    for line in output.splitlines():
        if not line.startswith("dongle"):
            continue
        parts = re.split(r"\s+", line.strip())
        if len(parts) < 13:
            continue
        dongle = parts[0]
        dongles[dongle] = {
            "state": parts[2],
            "rssi": parts[3],
            "provider": parts[6],
            "model": parts[7],
            "imei": parts[9] if len(parts) > 9 else "",
            "imsi": parts[10] if len(parts) > 10 else "",
            "number": parts[12] if len(parts) > 12 else "",
        }
    return dongles


def parse_dongle_setting(output):
    settings = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        settings[key.strip()] = val.strip()
    return settings


def parse_env(path):
    if not path.exists():
        return {}
    text = path.read_text(errors="ignore")
    match = re.search(r"DEVICES=(\[.*\])", text)
    if not match:
        return {}
    try:
        devices = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return {item["dongle_name"]: item.get("number", "") for item in devices if "dongle_name" in item}


def format_line(port, dongle, number, state, env_number, model):
    if number:
        number = number.strip()
    else:
        number = "<sem número>"
    if env_number:
        env_number = env_number.strip()
    else:
        env_number = "<sem env>"
    return f"{port:14}  {dongle:8}  {state:12}  {model:8}  {number:20}  env={env_number}"


def main():
    asterisk_out = run_cmd(["sudo", "asterisk", "-rx", "dongle show devices"])
    dongles = parse_dongle_devices(asterisk_out)
    env_numbers = parse_env(ENV_FILE)

    rows = []
    for dongle, info in sorted(dongles.items()):
        setting_out = run_cmd(["sudo", "asterisk", "-rx", f"dongle show device settings {dongle}"])
        settings = parse_dongle_setting(setting_out)
        port = settings.get("Data", "<desconhecido>")
        model = info.get("model", "")
        rows.append((port, dongle, info["number"], info["state"], env_numbers.get(dongle, ""), model))

    rows.sort(key=lambda r: (r[0] != "<desconhecido>", r[0]))

    print("PORT             DONGLE    STATE         MODEL     NUMBER               ENV_NUMBER")
    print("-----------------------------------------------------------------------------------")
    for port, dongle, number, state, env_number, model in rows:
        print(format_line(port, dongle, number, state, env_number, model))

    print("\nSe quiser atualizar asterisk/dongle.conf com esses dados, use tools/update_dongle_conf.py")


if __name__ == '__main__':
    main()
