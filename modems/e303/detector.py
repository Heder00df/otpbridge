import re
import subprocess

# Códigos USSD por operadora, em ordem de tentativa.
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
    Retorna lista de (mm_index, number) para todos os modems detectados.
    Usa IMEI como chave estável — o índice MM:X pode mudar a cada restart,
    mas o IMEI é fixo no hardware.
    """
    result = subprocess.run(["mmcli", "-L"], capture_output=True, text=True)
    modems = []
    for line in result.stdout.splitlines():
        m = re.search(r"/Modem/(\d+)", line)
        if not m:
            continue
        idx = int(m.group(1))
        number = _get_number_for_modem(idx)
        modems.append((idx, number))
    return modems


def _get_number_for_modem(mm_index: int) -> str:
    """
    Resolve o número do modem usando IMEI como chave estável.
    Fluxo:
      1. Lê IMEI do modem via mmcli
      2. Busca no banco pelo IMEI — se achou, atualiza porta_usb e retorna número
      3. Se não achou, roda USSD de todas as operadoras
      4. Salva no banco com IMEI como chave
      5. Fallback: unknown-{mm_index}
    """
    imei = _get_imei(mm_index)
    if not imei:
        return f"unknown-{mm_index}"

    # Atualiza porta_usb para o índice atual (MM pode ter mudado)
    porta = f"MM:{mm_index}"
    number = _lookup_by_imei(imei, porta)
    if number:
        return number

    # Número não está no banco — descobrir via USSD
    number = _ussd_all_operators(mm_index, imei)
    if number:
        return number

    return f"unknown-{mm_index}"


def _get_imei(mm_index: int) -> str:
    try:
        r = subprocess.run(["mmcli", "-m", str(mm_index)],
                           capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            if "imei:" in line:
                return line.split("imei:")[-1].strip()
    except Exception:
        pass
    return ""


def _get_own_number(mm_index: int) -> str:
    """Lê o número gravado no SIM (CNUM). Fallback quando USSD não responde."""
    try:
        r = subprocess.run(["mmcli", "-m", str(mm_index)],
                           capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            if "own:" in line:
                num = line.split("own:")[-1].strip().lstrip("+")
                if num and len(num) >= 10:
                    return _normalize(num)
    except Exception:
        pass
    return ""


def _lookup_by_imei(imei: str, porta_atual: str) -> str:
    """Busca número pelo IMEI e atualiza porta_usb se o índice MM mudou."""
    try:
        from db.repository import _engine as engine
        from sqlalchemy import text
        with engine.begin() as conn:
            row = conn.execute(text(
                "SELECT id, numero, porta_usb FROM modems WHERE imei = :imei"
            ), {"imei": imei}).fetchone()
            if row and row[1] and not row[1].startswith("unknown"):
                if row[2] != porta_atual:
                    conn.execute(text(
                        "UPDATE modems SET porta_usb = :porta WHERE imei = :imei"
                    ), {"porta": porta_atual, "imei": imei})
                    print(f"[Detector] IMEI {imei}: porta atualizada {row[2]} → {porta_atual}")
                return row[1]
    except Exception as e:
        print(f"[Detector] erro ao buscar IMEI {imei}: {e}")
    return ""


def _ussd_all_operators(mm_index: int, imei: str) -> str:
    for operadora, codigo, pattern in _USSD_OPERATORS:
        number = _ussd_query(mm_index, codigo, pattern)
        if number:
            print(f"[Detector] MM:{mm_index} IMEI:{imei} → {number} ({operadora} via {codigo})")
            _save_to_db(mm_index, imei, number)
            return number

    # Fallback: número gravado no SIM (CNUM) — menos confiável em chips M2M
    number = _get_own_number(mm_index)
    if number:
        print(f"[Detector] MM:{mm_index} IMEI:{imei} → {number} (CNUM fallback)")
        _save_to_db(mm_index, imei, number)
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
    num = num.lstrip("+")
    if not num.startswith("55"):
        num = "55" + num
    return num


def _save_to_db(mm_index: int, imei: str, number: str):
    try:
        from db.repository import _engine as engine
        from sqlalchemy import text
        porta = f"MM:{mm_index}"
        with engine.begin() as conn:
            # Upsert por IMEI
            existing = conn.execute(text(
                "SELECT id FROM modems WHERE imei = :imei"
            ), {"imei": imei}).fetchone()
            if existing:
                conn.execute(text(
                    "UPDATE modems SET numero = :num, porta_usb = :porta WHERE imei = :imei"
                ), {"num": number, "porta": porta, "imei": imei})
            else:
                conn.execute(text(
                    "UPDATE modems SET imei = :imei, numero = :num, porta_usb = :porta "
                    "WHERE porta_usb = :porta AND imei IS NULL"
                ), {"imei": imei, "num": number, "porta": porta})
    except Exception as e:
        print(f"[Detector] erro ao salvar IMEI {imei}: {e}")
