import subprocess
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text

router = APIRouter()

_HTML = Path(__file__).parent / "index.html"


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return _HTML.read_text()


@router.get("/dashboard/api/status")
async def status(request: Request):
    pool = getattr(request.app.state, "modem_pool", None)
    modems = []
    if pool:
        import re as _re
        for w in pool.modems.values():
            signal = 0
            usb_port = ""
            tty_port = ""
            try:
                r = subprocess.run(
                    ["mmcli", "-m", str(w.mm_index)],
                    capture_output=True, text=True, timeout=5
                )
                for line in r.stdout.splitlines():
                    if "signal quality:" in line:
                        m = _re.search(r"(\d+)%", line)
                        if m:
                            signal = int(m.group(1))
                    if "device:" in line and "sys/devices" in line:
                        m = _re.search(r"usb\d+/([0-9\-\.]+)$", line)
                        if m:
                            usb_port = m.group(1)
                    if "primary port:" in line:
                        tty_port = line.split("primary port:")[-1].strip()
            except Exception:
                pass
            modems.append({
                "modem_id":  w.modem_id,
                "mm_index":  w.mm_index,
                "number":    w.number,
                "status":    w.status,
                "signal":    signal,
                "usb_port":  usb_port,
                "tty_port":  tty_port,
                "activation_id": w.activation_id,
            })

    from db.repository import _engine as engine
    with engine.connect() as conn:
        hoje = conn.execute(text(
            "SELECT COUNT(*) FROM ativacoes WHERE criado_em >= CURRENT_DATE"
        )).scalar()
        sms_hoje = conn.execute(text(
            "SELECT COUNT(*) FROM sms_log WHERE criado_em >= CURRENT_DATE"
        )).scalar()
        ultimos_sms = conn.execute(text(
            "SELECT s.criado_em, m.porta_usb, m.numero, s.texto_bruto, s.codigo "
            "FROM sms_log s LEFT JOIN modems m ON m.id = s.modem_id "
            "ORDER BY s.criado_em DESC LIMIT 10"
        )).fetchall()

    return JSONResponse({
        "modems": sorted(modems, key=lambda x: x["mm_index"]),
        "stats": {
            "ativacoes_hoje": hoje,
            "sms_hoje": sms_hoje,
            "total_modems": len(modems),
            "modems_livres": sum(1 for m in modems if m["status"] == "FREE"),
        },
        "ultimos_sms": [
            {
                "hora":   str(r[0])[:19],
                "porta":  r[1] or "?",
                "numero": r[2] or "?",
                "texto":  r[3],
                "codigo": r[4],
            }
            for r in ultimos_sms
        ],
    })


@router.post("/dashboard/api/redescobrir")
async def redescobrir():
    """Força redescoberta de números via USSD em todos os modems."""
    try:
        from modems.e303.detector import detect_modems
        result = detect_modems()
        return {"ok": True, "modems": [{"mm": idx, "number": num} for idx, num in result]}
    except Exception as e:
        return JSONResponse({"ok": False, "erro": str(e)}, status_code=500)


@router.post("/dashboard/api/enviar-sms")
async def enviar_sms(request: Request):
    body = await request.json()
    mm_index = body.get("mm_index")
    destino  = str(body.get("destino", "")).strip()
    texto    = str(body.get("texto", "")).strip().replace(" ", "-")

    if not mm_index or not destino or not texto:
        return JSONResponse({"ok": False, "erro": "Campos obrigatórios: mm_index, destino, texto"}, status_code=400)

    # Garante prefixo +55
    if not destino.startswith("+"):
        destino = f"+55{destino}" if not destino.startswith("55") else f"+{destino}"

    try:
        # Cria SMS via mmcli
        r = subprocess.run(
            ["mmcli", "-m", str(mm_index),
             f"--messaging-create-sms=number={destino},text={texto}"],
            capture_output=True, text=True, timeout=10
        )
        import re
        sms_obj = re.search(r"/org/freedesktop/ModemManager1/SMS/\d+", r.stdout)
        if not sms_obj:
            return JSONResponse({"ok": False, "erro": r.stderr or "Falha ao criar SMS"}, status_code=500)

        # Envia
        s = subprocess.run(
            ["mmcli", "--sms", sms_obj.group(), "--send"],
            capture_output=True, text=True, timeout=15
        )
        if "successfully" in s.stdout:
            return {"ok": True}
        return JSONResponse({"ok": False, "erro": s.stderr or s.stdout}, status_code=500)
    except Exception as e:
        return JSONResponse({"ok": False, "erro": str(e)}, status_code=500)


@router.post("/dashboard/api/reiniciar")
async def reiniciar():
    """Reinicia o serviço OTPBridge via systemctl."""
    try:
        subprocess.run(["sudo", "systemctl", "restart", "otpbridge"],
                       check=True, timeout=15)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "erro": str(e)}, status_code=500)


@router.post("/dashboard/api/config")
async def salvar_config(request: Request):
    """Atualiza chaves no .env sem reiniciar (requer restart para efetivar)."""
    body = await request.json()
    env_path = Path("/opt/otpbridge/.env")
    if not env_path.exists():
        env_path = Path(__file__).parent.parent.parent / ".env"

    lines = env_path.read_text().splitlines()
    updates = {k: v for k, v in body.items() if k in ("HEROSMS_KEY", "SUPPLIER_KEY")}

    new_lines = []
    for line in lines:
        key = line.split("=")[0] if "=" in line else ""
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            updates.pop(key)
        else:
            new_lines.append(line)

    env_path.write_text("\n".join(new_lines) + "\n")
    return {"ok": True, "aviso": "Reinicie o serviço para aplicar as mudanças."}
