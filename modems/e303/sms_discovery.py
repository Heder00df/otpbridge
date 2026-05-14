"""
Auto-discovery de números reais via SMS.
Fluxo:
  1. Escolhe o modem com melhor sinal como receptor
  2. Todos os outros enviam SMS para ele com texto "ID:MM{idx}"
  3. O receptor captura os SMS e mapeia remetente → MM:X
  4. Atualiza o banco com os números reais
"""
import re
import subprocess
import threading
import time
from typing import Optional

_session: Optional["DiscoverySession"] = None
_lock = threading.Lock()


def get_session() -> Optional["DiscoverySession"]:
    return _session


class DiscoverySession:
    def __init__(self, receiver_mm: int, receiver_number: str, targets: list[dict]):
        self.receiver_mm = receiver_mm
        self.receiver_number = receiver_number
        self.targets = targets          # [{mm_index, number}]
        self.results: dict[str, str] = {}  # from_number → mm_index
        self.done = False
        self.errors: list[str] = []
        self.total = len(targets)
        self.sent = 0

    def to_dict(self) -> dict:
        return {
            "receiver_mm":     self.receiver_mm,
            "receiver_number": self.receiver_number,
            "total":   self.total,
            "sent":    self.sent,
            "done":    self.done,
            "results": self.results,
            "errors":  self.errors,
        }


def start_discovery(pool) -> dict:
    global _session
    with _lock:
        if _session and not _session.done:
            return {"ok": False, "erro": "Discovery já em andamento."}

        # Escolhe receptor: modem FREE com maior sinal
        best = None
        best_signal = -1
        for w in pool.modems.values():
            if w.number.startswith("unknown"):
                continue
            sig = _get_signal(w.mm_index)
            if sig > best_signal:
                best_signal = sig
                best = w

        if not best:
            return {"ok": False, "erro": "Nenhum modem disponível como receptor."}

        targets = [
            {"mm_index": w.mm_index, "number": w.number}
            for w in pool.modems.values()
            if w.modem_id != best.modem_id and not w.number.startswith("unknown")
        ]

        if not targets:
            return {"ok": False, "erro": "Nenhum modem para enviar."}

        _session = DiscoverySession(
            receiver_mm=best.mm_index,
            receiver_number=best.number,
            targets=targets,
        )

        # Inicia envios em background
        threading.Thread(target=_run_discovery, args=(_session,), daemon=True).start()

        return {"ok": True, "session": _session.to_dict()}


def record_sms(receiver_mm: int, from_number: str, text: str):
    """Chamado pelo worker quando SMS chega. Registra se for mensagem de discovery."""
    with _lock:
        if not _session or _session.receiver_mm != receiver_mm:
            return
        m = re.search(r"ID:MM(\d+)", text)
        if not m:
            return
        mm_idx = int(m.group(1))
        _session.results[str(mm_idx)] = from_number
        print(f"[Discovery] MM:{mm_idx} → {from_number}")
        _save_number(mm_idx, from_number)


def _run_discovery(session: DiscoverySession):
    time.sleep(1)
    for t in session.targets:
        texto = f"ID:MM{t['mm_index']}"
        ok = _send_sms(t["mm_index"], session.receiver_number, texto)
        if ok:
            session.sent += 1
        else:
            session.errors.append(f"MM:{t['mm_index']} falhou ao enviar")
        time.sleep(3)  # evita flood

    # Aguarda até 60s para receber as respostas
    deadline = time.time() + 60
    while time.time() < deadline:
        with _lock:
            if len(session.results) >= session.total:
                break
        time.sleep(2)

    session.done = True
    print(f"[Discovery] concluído — {len(session.results)}/{session.total} números descobertos")


def _send_sms(mm_index: int, destino: str, texto: str) -> bool:
    if not destino.startswith("+"):
        destino = f"+{destino}"
    try:
        r = subprocess.run(
            ["mmcli", "-m", str(mm_index),
             f"--messaging-create-sms=number={destino},text={texto}"],
            capture_output=True, text=True, timeout=10
        )
        m = re.search(r"/org/freedesktop/ModemManager1/SMS/\d+", r.stdout)
        if not m:
            return False
        s = subprocess.run(
            ["mmcli", "--sms", m.group(), "--send"],
            capture_output=True, text=True, timeout=15
        )
        return "successfully" in s.stdout
    except Exception as e:
        print(f"[Discovery] erro ao enviar MM:{mm_index} → {e}")
        return False


def _get_signal(mm_index: int) -> int:
    try:
        r = subprocess.run(["mmcli", "-m", str(mm_index)],
                           capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if "signal quality:" in line:
                m = re.search(r"(\d+)%", line)
                if m:
                    return int(m.group(1))
    except Exception:
        pass
    return 0


def _save_number(mm_index: int, number: str):
    try:
        from db.repository import _engine as engine
        from sqlalchemy import text
        porta = f"MM:{mm_index}"
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE modems SET numero = :num WHERE porta_usb = :porta"
            ), {"num": number, "porta": porta})
        print(f"[Discovery] banco atualizado: MM:{mm_index} → {number}")
    except Exception as e:
        print(f"[Discovery] erro ao salvar: {e}")
