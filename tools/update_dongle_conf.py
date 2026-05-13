#!/usr/bin/env python3
"""Atualiza automaticamente a configuração de dongles em asterisk/dongle.conf.

O script faz:
  1. Lê `asterisk/dongle.conf` e identifica os blocos [dongleX].
  2. Consulta o Asterisk para `dongle show device settings dongleX` e obtém o `Data`.
  3. Consulta `sudo asterisk -rx "dongle show devices"` para obter o número atual do dongle.
  4. Atualiza `data=/dev/ttyUSB*` no arquivo e a linha `; number=...` dentro do bloco.
  5. Mantém `audio=/dev/null` e atualiza apenas o comentário `original: /dev/ttyUSB*` se existir.

Uso:
  python3 tools/update_dongle_conf.py

Opções:
  --dry-run   mostra as alterações sem gravar.
"""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DONGLE_CONF = ROOT / "asterisk" / "dongle.conf"
ENV_FILE = ROOT / ".env"


def run_command(command):
    result = subprocess.run(command, capture_output=True, text=True)
    return result.stdout


def parse_asterisk_devices(output):
    devices = {}
    for line in output.splitlines():
        if not line.startswith("dongle"):
            continue
        parts = re.split(r"\s+", line.strip())
        if len(parts) < 13:
            continue
        dongle = parts[0]
        number = parts[12]
        devices[dongle] = number
    return devices


def parse_dongle_settings(output):
    settings = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        settings[key.strip()] = value.strip()
    return settings


def parse_env_numbers(path):
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


def get_ports_from_asterisk(dongles):
    ports = {}
    for dongle in dongles:
        output = run_command(["sudo", "asterisk", "-rx", f"dongle show device settings {dongle}"])
        if not output:
            continue
        settings = parse_dongle_settings(output)
        data = settings.get("Data")
        if data:
            ports[dongle] = data
    return ports


def load_dongle_conf(path):
    text = path.read_text(errors="ignore")
    lines = text.splitlines()
    return lines


def update_section(lines, section, data_port, number):
    updated = []
    current_section = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1]
        if current_section != section:
            continue

        if stripped.startswith("data=") and data_port:
            updated.append((idx, f"data={data_port}"))

        if stripped.startswith("audio=") and data_port:
            # Preserve audio=/dev/null but update original comment if present.
            if "; original:" in line:
                prefix = line.split("; original:", 1)[0].rstrip()
                updated.append((idx, f"{prefix} ; original: {data_port}"))

        if stripped.startswith("; number=") and number is not None:
            updated.append((idx, f"; number={number}"))

    return updated


def apply_updates(lines, updates):
    for idx, new_line in sorted(updates, key=lambda x: x[0], reverse=False):
        lines[idx] = new_line
    return lines


def main():
    parser = argparse.ArgumentParser(description="Atualiza asterisk/dongle.conf com portas e números reais.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra as alterações sem gravar")
    args = parser.parse_args()

    if not DONGLE_CONF.exists():
        raise SystemExit(f"Arquivo não encontrado: {DONGLE_CONF}")

    env_numbers = parse_env_numbers(ENV_FILE)
    asterisk_output = run_command(["sudo", "asterisk", "-rx", "dongle show devices"])
    asterisk_numbers = parse_asterisk_devices(asterisk_output)

    section_names = [m.group(1) for m in re.finditer(r"^\[(dongle\d+)\]", DONGLE_CONF.read_text(errors="ignore"), re.MULTILINE)]
    data_ports = get_ports_from_asterisk(section_names)

    lines = load_dongle_conf(DONGLE_CONF)
    all_updates = []

    for section in section_names:
        port = data_ports.get(section)
        number = asterisk_numbers.get(section)
        if not number or number.lower() == "unknown":
            number = env_numbers.get(section)
        if port:
            updates = update_section(lines, section, port, number)
            all_updates.extend(updates)

    if not all_updates:
        print("Nenhuma atualização encontrada.")
        return

    new_lines = apply_updates(lines, all_updates)

    if args.dry_run:
        print("=== Alterações propostas ===")
        for idx, new_line in all_updates:
            print(f"{idx+1}: {new_line}")
        return

    DONGLE_CONF.write_text("\n".join(new_lines) + "\n")
    print(f"Arquivo atualizado: {DONGLE_CONF}")


if __name__ == "__main__":
    main()
