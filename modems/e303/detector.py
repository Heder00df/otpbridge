import re
import subprocess

# Códigos USSD por operadora, em ordem de tentativa.
# Cada entrada: (operadora, código, regex para extrair o número da resposta)
_USSD_OPERATORS = [
    ("TIM",   "*846#",  r"\[(\d{8,13})\]"),
    ("Claro", "*510#",  r"\b(\d{10,13})\b"),
    ("Claro", "*544#",  r"\b(\d{10,13})\b"),
    ("Vivo",  "*8486#", r"\b(\d{10,13})\b"),
    ("Oi",    "*880#",  r"\b(\d{10,13})\b"),
    ("Oi",    "*461#",  r"\b(\d{10,13})\b"),
]


def detect_modems() -> list[tuple[int, str]]:
    """
    Retorna lista de (mm_index, number) para todos os modems detectados
    pelo ModemManager. Prioriza número salvo no banco, depois tenta USSD
    de todas as operadoras, depois CNUM do SIM como último recurso.
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
    number = _ussd_all_operators(mm_index)
    if number:
        return number

    # Último recurso: CNUM gravado no SIM (falha em chips M2M)
    r = subprocess.run(["mmcli", "-m", str(mm_index)], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if "own:" in line:
            num = line.split("own:")[-1].strip().lstrip("+")
            if num and not num.startswith("unknown"):
                return _normalize(num)
    return f"unknown-{mm_index}"


def _ussd_all_operators(mm_index: int) -> str:
    """
    Tenta cada operadora em sequência e retorna o primeiro número válido.
    Salva no banco assim que encontrar, para não precisar repetir na próxima inicialização.
    """
    for operadora, codigo, pattern in _USSD_OPERATORS:
        number = _ussd_query(mm_index, codigo, pattern)
        if number:
            print(f"[Detector] MM:{mm_index} → {number} ({operadora} via {codigo})")
            _save_to_db(mm_index, number)
            return number
    return ""


def _ussd_query(mm_index: int, codigo: str, pattern: str) -> str:
    try:
        r = subprocess.run(
            ["mmcli", "-m", str(mm_index), f"--3gpp-ussd-initiate={codigo}"],
            capture_output=True, text=True, timeout=20,
        )
        m = re.search(pattern, r.stdout)
        if m:
            return _normalize(m.group(1))
    except Exception:
        pass
    return ""


def _normalize(num: str) -> str:
    """Garante prefixo 55 (Brasil) e remove +."""
    num = num.lstrip("+")
    if not num.startswith("55"):
        num = "55" + num
    return num


def _save_to_db(mm_index: int, number: str):
    """Persiste o número descoberto para não ter que consultar USSD na próxima vez."""
    try:
        from db.repository import _engine as engine
        from sqlalchemy import text
        porta = f"MM:{mm_index}"
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE modems SET numero = :num WHERE porta_usb = :porta"
            ), {"num": number, "porta": porta})
    except Exception as e:
        print(f"[Detector] erro ao salvar número no banco: {e}")
