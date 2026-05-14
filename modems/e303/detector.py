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


def detect_modems() -> list[tuple[int, str, int]]:
    """
    Retorna lista de (mm_index, number, db_id) para todos os modems detectados.
    Usa IMEI como chave estável — o índice MM:X pode mudar a cada restart,
    mas o IMEI é fixo no hardware. db_id é o id real na tabela modems.
    """
    result = subprocess.run(["mmcli", "-L"], capture_output=True, text=True)
    modems = []
    for line in result.stdout.splitlines():
        m = re.search(r"/Modem/(\d+)", line)
        if not m:
            continue
        idx = int(m.group(1))
        number, db_id = _get_number_and_id_for_modem(idx)
        modems.append((idx, number, db_id))
    return modems


def _get_number_and_id_for_modem(mm_index: int) -> tuple[str, int]:
    """
    Resolve o número e o db_id do modem usando IMEI como chave estável.
    Fluxo:
      1. Lê IMEI do modem via mmcli
      2. Busca no banco pelo IMEI — se achou, atualiza porta_usb e retorna número
      3. Se não achou, roda USSD de todas as operadoras
      4. Salva no banco com IMEI como chave
      5. Fallback: unknown-{mm_index}
    """
    imei = _get_imei(mm_index)
    if not imei:
        return f"unknown-{mm_index}", 0

    porta = f"MM:{mm_index}"
    number, db_id = _lookup_by_imei(imei, porta)
    if number:
        return number, db_id

    number = _ussd_all_operators(mm_index, imei)
    if number:
        db_id = _get_db_id_by_imei(imei)
        return number, db_id

    return f"unknown-{mm_index}", 0


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
                return row[1], row[0]
    except Exception as e:
        print(f"[Detector] erro ao buscar IMEI {imei}: {e}")
    return "", 0


def _get_db_id_by_imei(imei: str) -> int:
    try:
        from db.repository import _engine as engine
        from sqlalchemy import text
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT id FROM modems WHERE imei = :imei"
            ), {"imei": imei}).fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


def _ussd_all_operators(mm_index: int, imei: str) -> str:
    """
    Tenta TIM → Claro → Vivo → Oi em ordem.
    Ao primeiro número encontrado, salva e passa pro próximo modem.
    Fallback: CNUM do SIM.
    """
    for operadora, codigo, pattern in _USSD_OPERATORS:
        # Cancela sessão USSD anterior se houver
        subprocess.run(["mmcli", "-m", str(mm_index), "--3gpp-ussd-cancel"],
                       capture_output=True, timeout=5)
        number = _ussd_query(mm_index, codigo, pattern)
        if number:
            print(f"[Detector] MM:{mm_index} IMEI:{imei} → {number} ({operadora} via {codigo})")
            _save_to_db(mm_index, imei, number)
            return number

    # Fallback: CNUM do SIM — não verificado
    number = _get_own_number(mm_index)
    if number:
        print(f"[Detector] MM:{mm_index} IMEI:{imei} → {number} (CNUM fallback — não verificado)")
        _save_to_db(mm_index, imei, number, verificado=False)
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


def _save_to_db(mm_index: int, imei: str, number: str, verificado: bool = True):
    try:
        from db.repository import _engine as engine
        from sqlalchemy import text
        porta = f"MM:{mm_index}"
        with engine.begin() as conn:
            existing = conn.execute(text(
                "SELECT id, numero FROM modems WHERE imei = :imei"
            ), {"imei": imei}).fetchone()

            if existing:
                old_number = existing[1]
                if old_number == number:
                    # Número igual — só atualiza porta e marca verificado se ainda não estava
                    conn.execute(text(
                        "UPDATE modems SET porta_usb = :porta, numero_verificado = :v WHERE imei = :imei"
                    ), {"porta": porta, "v": verificado, "imei": imei})
                else:
                    # Número mudou — atualiza e marca verificado
                    print(f"[Detector] MM:{mm_index} número atualizado: {old_number} → {number}")
                    conn.execute(text(
                        "UPDATE modems SET numero = :num, porta_usb = :porta, "
                        "numero_verificado = :v WHERE imei = :imei"
                    ), {"num": number, "porta": porta, "v": verificado, "imei": imei})
                return

            # Aproveita registro órfão se existir
            orphan = conn.execute(text(
                "SELECT id FROM modems WHERE imei IS NULL AND porta_usb IS NULL LIMIT 1"
            )).fetchone()
            if orphan:
                conn.execute(text(
                    "UPDATE modems SET imei = :imei, numero = :num, porta_usb = :porta, "
                    "numero_verificado = :v WHERE id = :id"
                ), {"imei": imei, "num": number, "porta": porta, "v": verificado, "id": orphan[0]})
                return

            # Insere novo — corrige sequência antes
            conn.execute(text(
                "SELECT setval('modems_id_seq', (SELECT MAX(id) FROM modems))"
            ))
            conn.execute(text(
                "INSERT INTO modems (imei, porta_usb, numero, hardware, suporta_voz, numero_verificado) "
                "VALUES (:imei, :porta, :num, 'e303', false, :v)"
            ), {"imei": imei, "porta": porta, "num": number, "v": verificado})
    except Exception as e:
        print(f"[Detector] erro ao salvar IMEI {imei}: {e}")
