from contextlib import contextmanager
from typing import Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL

_engine = create_engine(DATABASE_URL, pool_pre_ping=True)
_Session = sessionmaker(bind=_engine)

@contextmanager
def session():
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()

# ── Modems ──────────────────────────────────────────────

def upsert_modem(modem_id: int, numero: str, hardware: str,
                 porta_usb: str = None, porta_audio: str = None,
                 suporta_voz: bool = False) -> None:
    with session() as s:
        s.execute(text("""
            INSERT INTO modems (id, numero, hardware, porta_usb, porta_audio, suporta_voz, status)
            VALUES (:id, :numero, :hardware, :porta_usb, :porta_audio, :suporta_voz, 'FREE')
            ON CONFLICT (id) DO UPDATE
              SET numero      = CASE
                                  WHEN modems.numero LIKE 'unknown%' THEN EXCLUDED.numero
                                  ELSE modems.numero
                                END,
                  hardware    = EXCLUDED.hardware,
                  porta_usb   = COALESCE(EXCLUDED.porta_usb, modems.porta_usb),
                  porta_audio = EXCLUDED.porta_audio,
                  suporta_voz = EXCLUDED.suporta_voz,
                  updated_at  = NOW()
        """), {"id": modem_id, "numero": numero, "hardware": hardware,
               "porta_usb": porta_usb, "porta_audio": porta_audio,
               "suporta_voz": suporta_voz})

def set_modem_status(modem_id: int, status: str, ativacao_id: str = None) -> None:
    with session() as s:
        s.execute(text("""
            UPDATE modems SET status = :status, ativacao_id = :ativacao_id, updated_at = NOW()
            WHERE id = :id
        """), {"id": modem_id, "status": status, "ativacao_id": ativacao_id})

# ── Ativações ────────────────────────────────────────────

def criar_ativacao(ativacao_id: str, modem_id: int, servico: str,
                   numero: str, pais: str = None) -> None:
    with session() as s:
        s.execute(text("""
            INSERT INTO ativacoes (id, modem_id, servico, numero, pais, status)
            VALUES (:id, :modem_id, :servico, :numero, :pais, 'AGUARDANDO')
        """), {"id": ativacao_id, "modem_id": modem_id,
               "servico": servico, "numero": numero, "pais": pais})

def atualizar_ativacao(ativacao_id: str, status: str,
                       tipo_otp: str = None, codigo: str = None) -> None:
    with session() as s:
        s.execute(text("""
            UPDATE ativacoes
               SET status          = :status,
                   tipo_otp        = COALESCE(:tipo_otp, tipo_otp),
                   codigo_recebido = COALESCE(:codigo, codigo_recebido),
                   concluido_em    = CASE WHEN :status IN ('CONCLUIDO','CANCELADO','TIMEOUT')
                                         THEN NOW() ELSE concluido_em END
             WHERE id = :id
        """), {"id": ativacao_id, "status": status,
               "tipo_otp": tipo_otp, "codigo": codigo})

# ── Logs ─────────────────────────────────────────────────

def log_sms(modem_id: int, ativacao_id: str, texto: str, codigo: Optional[str]) -> int:
    with session() as s:
        row = s.execute(text("""
            INSERT INTO sms_log (modem_id, ativacao_id, texto_bruto, codigo)
            VALUES (:modem_id, :ativacao_id, :texto, :codigo)
            RETURNING id
        """), {"modem_id": modem_id, "ativacao_id": ativacao_id,
               "texto": texto, "codigo": codigo}).fetchone()
        return row[0]

def log_voz(modem_id: int, ativacao_id: str, transcricao: str,
            codigo: Optional[str], duracao: int) -> None:
    with session() as s:
        s.execute(text("""
            INSERT INTO voz_log (modem_id, ativacao_id, transcricao, codigo, duracao_seg)
            VALUES (:modem_id, :ativacao_id, :transcricao, :codigo, :duracao)
        """), {"modem_id": modem_id, "ativacao_id": ativacao_id,
               "transcricao": transcricao, "codigo": codigo, "duracao": duracao})

def log_evento(tipo: str, modem_id: int = None,
               ativacao_id: str = None, detalhe: str = None) -> None:
    with session() as s:
        s.execute(text("""
            INSERT INTO eventos (modem_id, ativacao_id, tipo, detalhe)
            VALUES (:modem_id, :ativacao_id, :tipo, :detalhe)
        """), {"modem_id": modem_id, "ativacao_id": ativacao_id,
               "tipo": tipo, "detalhe": detalhe})
