#!/usr/bin/env python3
"""Lista dongles Asterisk e portas USB para E303.

Mostra:
  - dongles Asterisk com número, IMSI/IMEI e estado
  - portas /dev/ttyUSB* disponíveis
  - links persistentes em /dev/serial/by-id e /dev/serial/by-path
  - mapeamento de dongle -> porta em asterisk/dongle.conf
  - número configurado em .env para cada dongle
"""

import json
import os
import re
import subprocess
from glob import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_command(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.stdout.strip()
    except Exception as exc:
        return f"ERROR: {exc}"


def parse_dongle_devices(output):
    devices = []
    for line in output.splitlines():
        if not line.startswith("dongle"):
            continue
        parts = re.split(r"\s+", line.strip())
        if len(parts) < 12:
            continue
        devices.append({
            "dongle": parts[0],
            "group": parts[1],
            "state": parts[2],
            "rssi": parts[3],
            "mode": parts[4],
            "submode": parts[5],
            "provider": parts[6],
            "name": parts[7],
            "model": parts[8],
            "firmware": parts[9],
            "imei": parts[10],
            "imsi": parts[11],
            "number": parts[12] if len(parts) >= 13 else "",
        })
    return devices


def parse_dongle_conf(path):
    mapping = {}
    if not path.exists():
        return mapping
    content = path.read_text(errors="ignore")
    current = None
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
        elif current and line.startswith("data="):
            mapping[current] = line.split("=", 1)[1].strip()
    return mapping


def parse_env_devices(path):
    if not path.exists():
        return {}
    text = path.read_text(errors="ignore")
    m = re.search(r"DEVICES=(\[.*\])", text)
    if not m:
        return {}
    try:
        devices = json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}
    return {d.get("dongle_name"): d.get("number") for d in devices if d.get("dongle_name")}


def list_serial_links(path):
    if not path.exists():
        return []
    return [f"{p.name} -> {os.readlink(p)}" for p in sorted(path.iterdir())]


def main():
    print("=== Asterisk dongle devices ===")
    output = run_command(["sudo", "asterisk", "-rx", "dongle show devices"])
    print(output or "(nenhum resultado)")
    print()

    devices = parse_dongle_devices(output)

    print("=== GPIO /dev/ttyUSB* ports ===")
    ports = sorted(glob("/dev/ttyUSB*"), key=lambda p: int(re.sub(r'[^0-9]', '', p)))
    for p in ports:
        print(p)
    if not ports:
        print("(nenhuma porta ttyUSB encontrada)")
    print()

    print("=== serial by-id ===")
    for line in list_serial_links(Path("/dev/serial/by-id")):
        print(line)
    if not list_serial_links(Path("/dev/serial/by-id")):
        print("(nenhum link by-id encontrado)")
    print()

    print("=== serial by-path ===")
    for line in list_serial_links(Path("/dev/serial/by-path")):
        print(line)
    if not list_serial_links(Path("/dev/serial/by-path")):
        print("(nenhum link by-path encontrado)")
    print()

    dongle_conf = parse_dongle_conf(ROOT / "asterisk" / "dongle.conf")
    env_numbers = parse_env_devices(ROOT / ".env")

    if dongle_conf:
        print("=== Mapeamento dongle.conf ===")
        for dongle, port in sorted(dongle_conf.items()):
            print(f"{dongle}: {port}")
        print()

    if env_numbers:
        print("=== Números em .env ===")
        for dongle, number in sorted(env_numbers.items()):
            print(f"{dongle}: {number}")
        print()

    if devices and dongle_conf:
        print("=== Resumo de mapeamento ===")
        for d in devices:
            print(
                f"{d['dongle']} -> {dongle_conf.get(d['dongle'], '???')} "
                f"number={d['number']} state={d['state']} imsi={d['imsi']} imei={d['imei']}"
            )

    print()
    print("Use este script para encontrar qual dongle está em qual porta e qual número está configurado.")


if __name__ == '__main__':
    main()
