#!/bin/bash
# Exibe ativações ativas com tempo de espera
# Uso: ./tools/check_busy.sh

cd "$(dirname "$0")/.." && source .venv/bin/activate && python3 - << 'EOF'
from db.repository import _engine as engine
from sqlalchemy import text

with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT id, servico, numero, status, criado_em, NOW()-criado_em as tempo "
        "FROM ativacoes WHERE status IN ('AGUARDANDO','SMS_RECEBIDO') ORDER BY criado_em"
    )).fetchall()

if not rows:
    print("Nenhuma ativação ativa.")
else:
    print(f"{'ID':<6} {'Serviço':<10} {'Número':<16} {'Status':<14} {'Tempo'}")
    print("─" * 65)
    for r in rows:
        print(f"{str(r[0]):<6} {r[1]:<10} {r[2]:<16} {r[3]:<14} {str(r[5]).split('.')[0]}")
    print("─" * 65)
    print(f"Total: {len(rows)} ativações ativas")
EOF
