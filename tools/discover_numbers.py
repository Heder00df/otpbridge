"""
Roda UMA vez para descobrir os números reais de todos os modems M2M.
O CNUM do SIM M2M costuma estar errado — este script envia um SMS
de cada modem para um número seu e pede que você informe o número
real que apareceu no celular.

Uso:
    cd /home/heder/dev/projetos/otpbridge
    source .venv/bin/activate
    python3 tools/discover_numbers.py +5561999342035
"""
import subprocess, time, sys, re, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    destination = sys.argv[1]
    modems = get_registered_modems()
    print(f"\n{len(modems)} modems registrados: {modems}\n")
    print(f"Enviando SMS de identificação para {destination}...\n")

    sent = []
    for idx in modems:
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

    mappings = {}
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
            if number.startswith("55") and len(number) > 11:
                number = number[2:]
            mappings[int(idx_str.strip())] = number
        except Exception:
            print("  Formato invalido -- use:  13:5585999920294")

    if not mappings:
        print("Nenhum mapeamento informado. Saindo.")
        sys.exit(0)

    print()
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
                print(f"  MM:{idx} -> {number}  OK (modem_id={row[0]})")
            else:
                print(f"  MM:{idx} -> porta {porta} nao encontrada no banco")

    print("\nNumeros atualizados. Reinicie o servidor para aplicar:")
    print("  pkill -f main.py && python3 main.py")
