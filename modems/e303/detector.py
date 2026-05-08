import re
import subprocess


def detect_modems() -> list[tuple[int, str]]:
    """
    Retorna lista de (mm_index, number) para todos os modems detectados
    pelo ModemManager. Prioriza número salvo no banco (corrigido manualmente)
    sobre o CNUM do SIM, que pode estar errado em chips M2M.
    """
    db_numbers = _load_db_numbers()

    result = subprocess.run(["mmcli", "-L"], capture_output=True, text=True)
    modems = []
    for line in result.stdout.splitlines():
        m = re.search(r"/Modem/(\d+)", line)
        if not m:
            continue
        idx = int(m.group(1))
        porta = f"MM:{idx}"
        number = db_numbers.get(porta) or _get_number_from_sim(idx)
        modems.append((idx, number))
    return modems


def _load_db_numbers() -> dict:
    """Carrega mapeamento porta_usb → numero do banco."""
    try:
        from db.repository import _engine as engine
        from sqlalchemy import text
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT porta_usb, numero FROM modems WHERE porta_usb IS NOT NULL"
            )).fetchall()
        result = {r[0]: r[1] for r in rows if r[1] and not r[1].startswith("unknown")}
        if result:
            print(f"[Detector] números do banco: {result}")
        return result
    except Exception as e:
        print(f"[Detector] erro ao carregar banco: {e}")
        return {}


def _get_number_from_sim(mm_index: int) -> str:
    # Tenta USSD *846# (TIM/roaming) — retorna número real da rede
    number = _ussd_number(mm_index)
    if number:
        return number

    # Fallback: CNUM do SIM (pode estar errado em chips M2M)
    r = subprocess.run(["mmcli", "-m", str(mm_index)], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if "own:" in line:
            num = line.split("own:")[-1].strip().lstrip("+")
            if num:
                return num
    return f"unknown-{mm_index}"


def _ussd_number(mm_index: int) -> str:
    """Consulta número real via USSD *846# (TIM). Retorna vazio se falhar."""
    try:
        r = subprocess.run(
            ["mmcli", "-m", str(mm_index), "--3gpp-ussd-initiate=*846#"],
            capture_output=True, text=True, timeout=20,
        )
        # Resposta: "Telefone [16988130896] nao Autorizado"
        m = re.search(r"\[(\d{8,13})\]", r.stdout)
        if m:
            num = m.group(1)
            # Garante prefixo 55 (Brasil)
            if not num.startswith("55"):
                num = "55" + num
            return num
    except Exception:
        pass
    return ""
