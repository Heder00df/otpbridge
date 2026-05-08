"""
Webhook para OpenVox GSM Gateway.
Configurar no painel OpenVox:
  SMS Notify URL: http://seuservidor:8000/openvox/sms
"""
from fastapi import APIRouter, Request
from modems.pool import get_pool

openvox_router = APIRouter()

@openvox_router.post("/openvox/sms")
async def openvox_sms(request: Request):
    data = await request.form()
    channel = int(data.get("channel", 1))
    text    = data.get("message", "")
    src     = data.get("caller", "")
    print(f"[OpenVox Webhook] canal={channel} de={src} texto={text}")

    pool = get_pool()
    worker = pool.find_by_line("openvox", channel)
    if worker:
        worker.deliver_sms(text)
    return {"status": "ok"}
