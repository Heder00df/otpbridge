import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional
from modems.base_worker import BaseModemWorker
from modems.factory import create_workers
from config import HARDWARE_TYPE, DEVICES
import db.repository as repo

_SERVICES_PATH = Path(__file__).parent.parent / "services.json"
_ALL_SERVICE_CODES = [s["code"] for s in json.loads(_SERVICES_PATH.read_text())]

_pool_instance: Optional["ModemPool"] = None

def _next_activation_id() -> int:
    from sqlalchemy import text
    with repo._engine.begin() as conn:
        return conn.execute(text("SELECT nextval('activation_id_seq')")).scalar()


def get_pool() -> "ModemPool":
    return _pool_instance

class ModemPool:
    def __init__(self):
        global _pool_instance
        self.modems: dict[int, BaseModemWorker] = {}
        self.lock = threading.Lock()
        _pool_instance = self

    def start(self):
        workers = create_workers(HARDWARE_TYPE, DEVICES, self._on_otp_received)
        for w in workers:
            w.start()
            self.modems[w.modem_id] = w
            repo.upsert_modem(
                modem_id=w.modem_id,
                numero=w.number,
                hardware=HARDWARE_TYPE,
                porta_usb=getattr(w, "port_at", None) or (
                    f"MM:{w.mm_index}" if hasattr(w, "mm_index") else None
                ),
                porta_audio=getattr(w, "port_audio", None),
                suporta_voz=False,
            )
            repo.log_evento("MODEM_ONLINE", modem_id=w.modem_id)
        print(f"[Pool] {len(self.modems)} modem(s) iniciado(s) — hardware: {HARDWARE_TYPE}")
        self._recuperar_ativacoes()
        threading.Thread(target=self._sync_estado, daemon=True).start()
        threading.Thread(target=self._verificar_numeros_busy, daemon=True).start()

    def _recuperar_ativacoes(self):
        """
        Ao reiniciar, restaura ativações AGUARDANDO/SMS_RECEBIDO nos workers corretos.
        Evita perder ativações em andamento quando o serviço reinicia.
        """
        try:
            from sqlalchemy import text
            with repo._engine.connect() as conn:
                rows = conn.execute(text(
                    "SELECT id, modem_id, servico FROM ativacoes "
                    "WHERE status IN ('AGUARDANDO', 'SMS_RECEBIDO') "
                    "ORDER BY criado_em DESC"
                )).fetchall()

            for activation_id, modem_id, servico in rows:
                w = self.modems.get(modem_id)
                if w and w.is_free():
                    w.activation_id = str(activation_id)
                    w.service = servico
                    w.status = "BUSY"
                    print(f"[Pool] Ativação {activation_id} restaurada → modem {modem_id}")
                else:
                    # Modem não encontrado ou ocupado — cancela a ativação
                    with repo._engine.begin() as conn:
                        conn.execute(text(
                            "UPDATE ativacoes SET status = 'CANCELADO' WHERE id = :id"
                        ), {"id": activation_id})
                    print(f"[Pool] Ativação {activation_id} cancelada (modem {modem_id} indisponível)")
        except Exception as e:
            print(f"[Pool] Erro ao recuperar ativações: {e}")

    def _sync_estado(self):
        """
        A cada 60s sincroniza o estado dos workers com o banco.
        Libera workers BUSY cuja ativação já foi finalizada no banco.
        Evita precisar reiniciar o serviço para limpar workers presos.
        """
        while True:
            time.sleep(60)
            try:
                from sqlalchemy import text
                with self.lock:
                    for w in self.modems.values():
                        if w.status != "BUSY" or not w.activation_id:
                            continue
                        with repo._engine.connect() as conn:
                            row = conn.execute(text(
                                "SELECT status FROM ativacoes WHERE id = :id"
                            ), {"id": w.activation_id}).fetchone()
                        if not row or row[0] in ("CONCLUIDO", "CANCELADO", "REEMBOLSADO"):
                            print(f"[Sync] Worker {w.modem_id} liberado — ativação {w.activation_id} já finalizada no banco")
                            w.activation_id = None
                            w.service = None
                            w.status = "FREE"
            except Exception as e:
                print(f"[Sync] erro: {e}")

    def _verificar_numeros_busy(self):
        """
        A cada 2 minutos verifica modems BUSY há mais de 10 minutos.
        Se o número mudou via USSD, cancela a ativação e libera o modem.
        O SMS nunca chegaria no número errado.
        """
        while True:
            time.sleep(120)
            try:
                from sqlalchemy import text
                from modems.e303.detector import _get_imei, _ussd_all_operators, _ussd_query
                import re

                with repo._engine.connect() as conn:
                    rows = conn.execute(text(
                        "SELECT id, modem_id, numero FROM ativacoes "
                        "WHERE status = 'AGUARDANDO' "
                        "AND criado_em < NOW() - INTERVAL '10 minutes'"
                    )).fetchall()

                for activation_id, modem_id, numero in rows:
                    w = self.modems.get(modem_id)
                    if not w or not hasattr(w, 'mm_index'):
                        continue

                    # Consulta número atual via USSD
                    subprocess.run(['mmcli', '-m', str(w.mm_index), '--3gpp-ussd-cancel'],
                                   capture_output=True, timeout=5)
                    numero_atual = _ussd_query(w.mm_index, "*846#", r"\[(\d{8,13})\]")
                    if not numero_atual:
                        continue

                    if not numero_atual.startswith("55"):
                        numero_atual = "55" + numero_atual

                    if numero_atual != numero:
                        print(f"[Pool] Número mudou MM:{w.mm_index}: {numero} → {numero_atual} — cancelando ativação {activation_id}")
                        with repo._engine.begin() as conn:
                            conn.execute(text(
                                "UPDATE ativacoes SET status = 'CANCELADO' WHERE id = :id"
                            ), {"id": activation_id})
                            conn.execute(text(
                                "UPDATE modems SET numero = :num, porta_usb = :porta WHERE id = :id"
                            ), {"num": numero_atual, "porta": f"MM:{w.mm_index}", "id": modem_id})
                        with self.lock:
                            w.number = numero_atual
                            w.activation_id = None
                            w.service = None
                            w.status = "FREE"
                    else:
                        print(f"[Pool] MM:{w.mm_index} número confirmado: {numero_atual}")
            except Exception as e:
                print(f"[Pool] verificar_numeros_busy erro: {e}")

    def stop(self):
        for w in self.modems.values():
            w.stop()
            repo.log_evento("MODEM_OFFLINE", modem_id=w.modem_id)

    def get_services(self) -> dict:
        with self.lock:
            free = sum(1 for m in self.modems.values() if m.is_free())
        return {
            "status": "success",
            "services": {code: free for code in _ALL_SERVICE_CODES},
        }

    def reserve_modem(self, service: str, country: Optional[str],
                      exception_set: list = None) -> Optional[dict]:
        exception_set = exception_set or []
        with self.lock:
            for w in self.modems.values():
                if not w.is_free():
                    continue
                if w.number.startswith("unknown"):
                    continue
                if not self._is_verified(w.modem_id):
                    continue
                # Rejeita números cujo prefixo está na lista de exceções
                if any(w.number.startswith(str(p)) for p in exception_set):
                    continue
                # Limita 4 usos por número por serviço por dia
                if self._usos_hoje(w.number, service) >= 4:
                    continue
                # ID numérico único via sequência do banco
                activation_id = str(_next_activation_id())
                w.reserve(activation_id, service)
                repo.set_modem_status(w.modem_id, "BUSY", activation_id)
                repo.criar_ativacao(activation_id, w.modem_id, service,
                                    w.number, pais=country)
                repo.log_evento("ATIVACAO_CRIADA", w.modem_id, activation_id,
                                f"servico={service} pais={country}")
                return {"activation_id": activation_id, "number": w.number}
        return None

    def _usos_hoje(self, numero: str, servico: str) -> int:
        try:
            from sqlalchemy import text
            with repo._engine.connect() as conn:
                return conn.execute(text(
                    "SELECT COUNT(*) FROM ativacoes "
                    "WHERE numero = :num AND servico = :svc "
                    "AND criado_em >= CURRENT_DATE"
                ), {"num": numero, "svc": servico}).scalar() or 0
        except Exception:
            return 0

    def _is_verified(self, modem_id: int) -> bool:
        try:
            from sqlalchemy import text
            with repo._engine.connect() as conn:
                row = conn.execute(text(
                    "SELECT numero_verificado FROM modems WHERE id = :id"
                ), {"id": modem_id}).fetchone()
                return bool(row and row[0])
        except Exception:
            return False

    def finish_activation(self, activation_id: str, status: int) -> str:
        # Mapeamento de status HeroSMS → label interno
        _STATUS_MAP = {
            1:  "CANCELADO",     # não fornecer mais números para este serviço
            3:  "CONCLUIDO",     # vendido com sucesso
            4:  "CANCELADO",     # cancelado (pode reusar até 4x)
            5:  "REEMBOLSADO",   # reembolso ao usuário
            14: "CONCLUIDO",     # aluguel vendido com sucesso
            15: "CANCELADO",     # aluguel cancelado
            16: "REEMBOLSADO",   # reembolso de aluguel
        }
        status_label = _STATUS_MAP.get(status, "CANCELADO")
        liberar = status in (3, 4, 5, 14, 15, 16)

        with self.lock:
            for w in self.modems.values():
                if w.activation_id == activation_id:
                    if liberar:
                        w.release(status)
                        repo.set_modem_status(w.modem_id, "FREE")
                    repo.atualizar_ativacao(activation_id, status_label)
                    repo.log_evento(status_label, w.modem_id, activation_id,
                                    f"herosms_status={status}")
                    return "OK"
        return "NOT_FOUND"

    def find_by_line(self, hardware: str, line: int) -> Optional[BaseModemWorker]:
        with self.lock:
            for w in self.modems.values():
                if hardware == "goip" and hasattr(w, "line") and w.line == line:
                    return w
                if hardware == "openvox" and hasattr(w, "channel") and w.channel == line:
                    return w
        return None

    def _on_otp_received(self, activation_id: str, code: str, otp_type: str):
        with self.lock:
            for w in self.modems.values():
                if w.activation_id == activation_id:
                    repo.log_evento("PUSH_OK", w.modem_id, activation_id,
                                    f"code={code} tipo={otp_type}")
                    break
