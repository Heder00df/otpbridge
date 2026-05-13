"""
Descoberta automática de números usando um dongle do próprio hub como receptor.

Fluxo:
  1. Escolhe um dongle receptor (padrão: dongle13, melhor sinal)
  2. Envia SMS de cada dongle para o número do receptor
  3. O receptor recebe os SMS com "OTPBridge ID:dongleX"
  4. Extrai o from_number de cada SMS recebido
  5. Atualiza o .env com os números reais

Uso:
    python3 tools/auto_discover.py
    python3 tools/auto_discover.py --receiver dongle5
"""
import sys
import os
import re
import json
import time
import subprocess
import requests
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL  = "http://localhost:8000"
WAIT_SECS = 120  # tempo para aguardar respostas


def get_dongles() -> list[str]:
    r = subprocess.run(
        ["sudo", "-n", "asterisk", "-rx", "dongle show devices"],
        capture_output=True, text=True
    )
    dongles = []
    for line in r.stdout.splitlines():
        m = re.match(r"(dongle\d+)\s+\d+\s+(\S+)", line)
        if m and m.group(2) == "Free":
            dongles.append(m.group(1))
    return dongles


def get_number(dongle: str) -> str:
    from config import DEVICES
    for d in DEVICES:
        if d["dongle_name"] == dongle:
            return d["number"]
    return ""


def send_sms(dongle: str, dest: str, text: str) -> bool:
    r = subprocess.run(
        ["sudo", "-n", "asterisk", "-rx", f"dongle sms {dongle} {dest} {text}"],
        capture_output=True, text=True
    )
    return "queued" in r.stdout


def update_env(mappings: dict):
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    with open(env_path) as f:
        content = f.read()

    from config import DEVICES
    devices = json.loads(re.search(r"DEVICES=(\[.*\])", content).group(1))

    updated = 0
    for d in devices:
        name = d["dongle_name"]
        if name in mappings and mappings[name]:
            num = re.sub(r"[^\d]", "", mappings[name])
            num = num.lstrip("0")
            if not num.startswith("55"):
                num = "55" + num
            if d["number"] != num:
                print(f"  {name}: {d['number']} → {num}")
                d["number"] = num
                updated += 1

    if updated:
        new_devices = json.dumps(devices, separators=(",", ":"))
        content = re.sub(r"DEVICES=\[.*\]", f"DEVICES={new_devices}", content)
        with open(env_path, "w") as f:
            f.write(content)
        print(f"\n{updated} número(s) atualizado(s) no .env")
    else:
        print("\nNenhum número novo para atualizar.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receiver", default="dongle13",
                        help="Dongle receptor (padrão: dongle13)")
    args = parser.parse_args()

    receiver = args.receiver
    receiver_number = get_number(receiver)

    if not receiver_number or receiver_number.startswith("unknown"):
        print(f"Erro: número do {receiver} não configurado no .env")
        sys.exit(1)

    dongles = get_dongles()
    senders = [d for d in dongles if d != receiver]

    print(f"\nReceptor: {receiver} ({receiver_number})")
    print(f"Enviando SMS de {len(senders)} dongles...\n")

    # Token único por sessão para evitar SMS atrasados de rodadas anteriores
    session_token = str(int(time.time()))[-4:]

    # Ativa modo descoberta no OTPBridge
    requests.post(f"{BASE_URL}/internal/discovery/start",
                  params={"receiver": receiver, "token": session_token})

    sent = []
    for d in senders:
        dest = f"+{receiver_number}" if not receiver_number.startswith("+") else receiver_number
        ok = send_sms(d, dest, f"OTPBridge ID:{d} T:{session_token}")
        status = "OK" if ok else "FALHOU"
        print(f"  {d} → {status}")
        if ok:
            sent.append(d)
        time.sleep(0.5)

    print(f"\n{len(sent)} SMS enviados. Aguardando respostas ({WAIT_SECS}s)...\n")

    # Aguarda com polling
    deadline = time.time() + WAIT_SECS
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/internal/discovery/results")
        results = r.json().get("results", {})
        remaining = [d for d in sent if d not in results]
        print(f"\r  Recebidos: {len(results)}/{len(sent)} — pendentes: {remaining}   ", end="", flush=True)
        if not remaining:
            break
        time.sleep(3)

    print()
    r = requests.get(f"{BASE_URL}/internal/discovery/results")
    results = r.json().get("results", {})

    if not results:
        print("Nenhuma resposta recebida.")
        sys.exit(1)

    print(f"\nResultados ({len(results)} dongles):")
    for dongle, number in sorted(results.items()):
        print(f"  {dongle} → {number}")

    missing = [d for d in sent if d not in results]
    if missing:
        print(f"\nSem resposta: {missing}")

    print("\nAtualizando .env...")
    update_env(results)

    print("\nReinicie o OTPBridge para aplicar:")
    print("  pkill -f main.py && python3 main.py")


if __name__ == "__main__":
    main()
