import re
import subprocess
import threading

# Códigos USSD por operadora para consulta do número real
_USSD_CODES = [
    ("TIM",   "*846#"),
    ("Claro", "*544#"),
    ("Oi",    "*461#"),
]

_USSD_TIMEOUT = 20  # segundos por consulta


def detect_modems() -> list[tuple[int, str]]:
    """
    Retorna lista de (mm_index, number) para todos os modems detectados
    pelo ModemManager. Prioriza número salvo no banco (corrigido manualmente)
    sobre o USSD das operadoras, que por sua vez tem prioridade sobre o CNUM
    do SIM (pode estar errado em chips M2M).
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
    """
    Tenta descobrir o número real na ordem:
      1. USSD de cada operadora em paralelo (TIM, Claro, Oi)
      2. CNUM do SIM como último recurso
    """
    number = _ussd_number_all(mm_index)
    if number:
        return number

    # Fallback: CNUM do SIM (pode estar errado em chips M2M)
    r = subprocess.run(["mmcli", "-m", str(mm_index)], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if "own:" in line:
            num = line.split("own:")[-1].strip().lstrip("+")
            if num:
                print(f"[Detector] MM:{mm_index} CNUM={num} (pode estar errado em M2M)")
                return num
    return f"unknown-{mm_index}"


def _ussd_number_all(mm_index: int) -> str:
    """
    Dispara USSD de todas as operadoras em paralelo.
    Retorna o primeiro número válido que chegar.
    """
    result = {"number": ""}
    found = threading.Event()
    lock = threading.Lock()

    def query(operadora: str, codigo: str):
        num = _ussd_query(mm_index, codigo)
        if num and not found.is_set():
            with lock:
                if not found.is_set():
                    result["number"] = num
                    found.set()
                    print(f"[Detector] MM:{mm_index} número via USSD {codigo} ({operadora}): {num}")

    threads = [
        threading.Thread(target=query, args=(op, cod), daemon=True)
        for op, cod in _USSD_CODES
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=_USSD_TIMEOUT + 2)

    return result["number"]


def _ussd_query(mm_index: int, codigo: str) -> str:
    """Executa um USSD e extrai o número da resposta. Retorna vazio se falhar."""
    try:
        r = subprocess.run(
            ["mmcli", "-m", str(mm_index), f"--3gpp-ussd-initiate={codigo}"],
            capture_output=True, text=True, timeout=_USSD_TIMEOUT,
        )
        m = re.search(r"\[(\d{8,13})\]", r.stdout)
        if m:
            num = m.group(1)
            if not num.startswith("55"):
                num = "55" + num
            return num
    except Exception:
        pass
    return ""
