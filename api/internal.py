from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

# discovery_mode: dongle_name do receptor → {dongle_remetente: from_number}
_discovery: Optional[dict] = None


def start_discovery(receiver_dongle: str, token: str = "") -> dict:
    global _discovery
    _discovery = {"receiver": receiver_dongle, "token": token, "results": {}}
    return _discovery


def stop_discovery() -> dict:
    global _discovery
    result = _discovery or {}
    _discovery = None
    return result


def record_discovery(receiver_dongle: str, from_number: str, text: str):
    """Chamado pelo webhook quando SMS chega no dongle receptor durante descoberta."""
    if not _discovery or _discovery["receiver"] != receiver_dongle:
        return
    import re
    token = _discovery.get("token", "")
    # valida token da sessão se presente
    if token and f"T:{token}" not in text:
        return
    m = re.search(r"ID:(dongle\d+)", text)
    if m:
        _discovery["results"][m.group(1)] = from_number
        print(f"[Discovery] {m.group(1)} → {from_number}")


@router.post("/internal/discovery/start")
async def discovery_start(receiver: str = "dongle13", token: str = ""):
    start_discovery(receiver, token)
    return {"ok": True, "receiver": receiver, "token": token}


@router.get("/internal/discovery/results")
async def discovery_results():
    return _discovery or {"receiver": None, "results": {}}


class VoiceDelivery(BaseModel):
    modem_number: str
    wav_path: str


@router.post("/internal/voice")
async def receive_voice(body: VoiceDelivery, request: Request):
    pool = request.app.state.modem_pool
    worker = pool.find_by_number(body.modem_number)
    if not worker:
        raise HTTPException(status_code=404, detail=f"modem {body.modem_number} não encontrado")
    worker.deliver_voice(body.wav_path)
    return {"ok": True}


class SmsDelivery(BaseModel):
    dongle_name: str
    from_number: str
    text: str


@router.post("/internal/sms")
async def receive_sms(body: SmsDelivery, request: Request):
    pool = request.app.state.modem_pool
    worker = pool.find_by_dongle(body.dongle_name)
    if not worker:
        raise HTTPException(status_code=404, detail=f"dongle {body.dongle_name} não encontrado")
    worker.deliver_sms(body.text)
    return {"ok": True}
