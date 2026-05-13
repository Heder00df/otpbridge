#!/usr/bin/env python3
"""Lista relação Modem → Número do banco de dados."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.repository import _engine as engine
from sqlalchemy import text

with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT porta_usb, numero FROM modems WHERE porta_usb IS NOT NULL ORDER BY porta_usb"
    )).fetchall()

def sort_key(r):
    try:
        return int(r[0].replace("MM:", ""))
    except Exception:
        return 999

rows = sorted(rows, key=sort_key)

print(f"{'Modem':<12} {'Número'}")
print("─" * 32)
for porta, numero in rows:
    print(f"{porta:<12} {numero}")
print("─" * 32)
print(f"Total: {len(rows)} modems")
