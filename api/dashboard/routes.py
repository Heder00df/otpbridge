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
            verificado = False
            try:
                with engine.connect() as c:
                    row = c.execute(text(
                        "SELECT numero_verificado FROM modems WHERE id = :id"
                    ), {"id": w.modem_id}).fetchone()
                    verificado = bool(row and row[0])
            except Exception:
                pass

            # Oculta modems não verificados das listagens
            if not verificado:
                continue

            modems.append({
                "modem_id":   w.modem_id,
                "mm_index":   w.mm_index,
                "number":     w.number,
                "status":     w.status,
                "signal":     signal,
                "usb_port":   usb_port,
                "tty_port":   tty_port,
                "verificado": verificado,
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


@router.post("/dashboard/api/discovery/start")
async def discovery_start(request: Request):
    pool = getattr(request.app.state, "modem_pool", None)
    if not pool:
        return JSONResponse({"ok": False, "erro": "Pool não iniciado."}, status_code=500)
    body = await request.json()
    external = body.get("external_number", "")
    from modems.e303.sms_discovery import start_discovery
    return start_discovery(pool, external_number=external)


@router.post("/dashboard/api/discovery/report")
async def discovery_report(request: Request):
    """Modo externo: usuário informa quais números chegaram no celular."""
    body = await request.json()
    # [{mm_index: 4, number: "5511999990001"}, ...]
    reports = body.get("reports", [])
    from modems.e303.sms_discovery import get_session, _save_number
    s = get_session()
    if not s:
        return JSONResponse({"ok": False, "erro": "Nenhuma sessão ativa."}, status_code=400)
    for r in reports:
        mm = int(r["mm_index"])
        num = str(r["number"]).strip().lstrip("+")
        if not num.startswith("55"):
            num = "55" + num
        s.results[str(mm)] = num
        _save_number(mm, num)
    s.done = True
    return {"ok": True, "atualizados": len(reports)}


@router.get("/dashboard/api/discovery/status")
async def discovery_status():
    from modems.e303.sms_discovery import get_session
    s = get_session()
    if not s:
        return {"active": False}
    return {"active": True, "session": s.to_dict()}


@router.post("/dashboard/api/redescobrir")
async def redescobrir(request: Request):
    """
    Força redescoberta via USSD.
    forcar=true: ignora cache do banco e refaz USSD em todos os modems.
    forcar=false (padrão): só descobre modems sem número.
    """
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    forcar = body.get("forcar", False)

    try:
        from modems.e303.detector import _get_imei, _ussd_all_operators, _get_db_id_by_imei, detect_modems
        import subprocess, re

        if forcar:
            result_usb = subprocess.run(["mmcli", "-L"], capture_output=True, text=True)
            resultados = []
            for line in result_usb.stdout.splitlines():
                m = re.search(r"/Modem/(\d+)", line)
                if not m:
                    continue
                idx = int(m.group(1))
                imei = _get_imei(idx)
                if not imei:
                    continue
                number = _ussd_all_operators(idx, imei)
                resultados.append({"mm": idx, "number": number or f"unknown-{idx}"})
            return {"ok": True, "modems": resultados}
        else:
            result = detect_modems()
            return {"ok": True, "modems": [{"mm": idx, "number": num} for idx, num, _ in result]}
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
        import re as _re
        import traceback

        # Cria SMS via mmcli
        r = subprocess.run(
            ["mmcli", "-m", str(mm_index),
             f"--messaging-create-sms=number={destino},text={texto}"],
            capture_output=True, text=True, timeout=10
        )
        print(f"[SMS] create stdout: {r.stdout!r}")
        print(f"[SMS] create stderr: {r.stderr!r}")
        print(f"[SMS] create returncode: {r.returncode}")

        sms_obj = _re.search(r"/org/freedesktop/ModemManager1/SMS/\d+", r.stdout)
        if not sms_obj:
            erro = r.stderr.strip() or r.stdout.strip() or "Falha ao criar SMS (sem output)"
            print(f"[SMS] ERRO criar: {erro}")
            return JSONResponse({"ok": False, "erro": erro}, status_code=500)

        # Envia em background para não travar a requisição
        sms_path = sms_obj.group()
        def _send():
            try:
                s = subprocess.run(
                    ["mmcli", "--sms", sms_path, "--send"],
                    capture_output=True, text=True, timeout=60
                )
                print(f"[SMS] send stdout: {s.stdout!r}")
                print(f"[SMS] send stderr: {s.stderr!r}")
                print(f"[SMS] send returncode: {s.returncode}")
            except Exception as ex:
                print(f"[SMS] send erro: {ex}")

        import threading
        threading.Thread(target=_send, daemon=True).start()
        return {"ok": True}
    except Exception as e:
        print(f"[SMS] EXCEPTION: {traceback.format_exc()}")
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
