"""
Descobre os números reais de todos os modems M2M.

Etapa 1 — automática: tenta USSD de cada operadora (TIM, Claro, Oi) em paralelo.
Etapa 2 — manual: para os modems que não responderam ao USSD, envia um SMS
           para um número seu e pede confirmação.

Uso:
    cd /home/heder/dev/projetos/otpbridge
    source .venv/bin/activate

    # Só USSD automático (sem SMS manual):
    python3 tools/discover_numbers.py

    # USSD automático + SMS manual para os que falharem:
    python3 tools/discover_numbers.py +5561999342035
"""
import subprocess, time, sys, re, os, threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modems.e303.detector import _ussd_number_all

_USSD_TIMEOUT = 22


def mmcli(*args):
    r = subprocess.run(["mmcli"] + list(args), capture_output=True, text=True)
    return r.stdout


def get_registered_modems():
    modems = []
    for line in mmcli("-L").splitlines():
        m = re.search(r"/Modem/(\d+)", line)
        if not m:
            continue
        idx = int(m.group(1))
        for l in mmcli("-m", str(idx)).splitlines():
            if "state:" in l and "power state" not in l and "packet service" not in l:
                if l.split("state:")[-1].strip() in ("registered", "connected"):
                    modems.append(idx)
    return modems


def send_sms(mm_index, destination, text):
    out = mmcli("-m", str(mm_index),
                f"--messaging-create-sms=text='{text}',number='{destination}'")
    m = re.search(r"(/org/freedesktop/ModemManager1/SMS/\d+)", out)
    if not m:
        return False
    r = subprocess.run(["mmcli", "--sms", m.group(1), "--send"],
                       capture_output=True, text=True)
    return "successfully sent" in r.stdout


def ussd_discover(modems: list[int]) -> dict[int, str]:
    """Consulta USSD de todas as operadoras em paralelo para cada modem."""
    results = {}
    lock = threading.Lock()

    def query(idx):
        number = _ussd_number_all(idx)
        with lock:
            results[idx] = number

    threads = [threading.Thread(target=query, args=(idx,), daemon=True) for idx in modems]
    total = len(threads)
    print(f"\nConsultando USSD em {total} modems (TIM *846#, Claro *544#, Oi *461#)...")
    print("Aguarde até ~20s por modem...\n")

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=_USSD_TIMEOUT)

    return results


def save_to_db(mappings: dict[int, str]):
    from db.repository import _engine as engine
    from sqlalchemy import text

    with engine.begin() as conn:
        for idx, number in mappings.items():
            porta = f"MM:{idx}"
            r = conn.execute(
                text("UPDATE modems SET numero=:n WHERE porta_usb=:p RETURNING id"),
                {"n": number, "p": porta},
            )
            row = r.fetchone()
            if row:
                print(f"  MM:{idx:2d} -> {number}  OK (modem_id={row[0]})")
            else:
                print(f"  MM:{idx:2d} -> porta {porta} não encontrada no banco")


if __name__ == "__main__":
    destination = sys.argv[1] if len(sys.argv) > 1 else None

    modems = get_registered_modems()
    print(f"{len(modems)} modems registrados: {modems}")

    # ── Etapa 1: USSD automático ──────────────────────────────
    ussd_results = ussd_discover(modems)

    found     = {idx: num for idx, num in ussd_results.items() if num}
    not_found = [idx for idx, num in ussd_results.items() if not num]

    print(f"\nResultado USSD:")
    for idx in sorted(ussd_results):
        num = ussd_results[idx]
        status = f"✓ {num}" if num else "✗ não respondeu"
        print(f"  MM:{idx:2d}  {status}")

    # ── Etapa 2: SMS manual para os que falharam ──────────────
    manual_mappings = {}

    if not_found:
        if not destination:
            print(f"\n{len(not_found)} modems sem número via USSD: {not_found}")
            print("Para descobri-los, rode novamente passando seu número:")
            print(f"  python3 tools/discover_numbers.py +5561999342035")
        else:
            print(f"\n{len(not_found)} modems sem resposta USSD: {not_found}")
            print(f"Enviando SMS de identificação para {destination}...\n")

            sent = []
            for idx in not_found:
                ok = send_sms(idx, destination, f"OTPBridge ID:{idx}")
                status = "OK" if ok else "FALHOU"
                print(f"  MM:{idx:2d}  ->  {status}")
                if ok:
                    sent.append(idx)
                time.sleep(1)

            print(f"\n{len(sent)} SMS enviados. Verifique seu celular.")
            print("Cada mensagem mostra o ID do modem (ex: 'OTPBridge ID:13').")
            print("Digite os mapeamentos no formato   MMID:numero   (um por linha).")
            print("Exemplo:  13:5585999920294")
            print("Pressione Enter em branco para finalizar.\n")

            while True:
                try:
                    line = input("> ").strip()
                except EOFError:
                    break
                if not line:
                    break
                try:
                    idx_str, number = line.split(":", 1)
                    number = re.sub(r"[^\d]", "", number)
                    if not number.startswith("55"):
                        number = "55" + number
                    manual_mappings[int(idx_str.strip())] = number
                except Exception:
                    print("  Formato inválido -- use:  13:5585999920294")

    # ── Salva tudo no banco ───────────────────────────────────
    all_mappings = {**found, **manual_mappings}

    if not all_mappings:
        print("\nNenhum número descoberto. Saindo.")
        sys.exit(0)

    print(f"\nSalvando {len(all_mappings)} números no banco...")
    save_to_db(all_mappings)

    if not_found and not manual_mappings:
        pending = [idx for idx in not_found if idx not in manual_mappings]
        print(f"\nAinda pendentes (sem número confirmado): {pending}")

    print("\nNúmeros atualizados. Reinicie o servidor para aplicar:")
    print("  pkill -f main.py && python3 main.py")
