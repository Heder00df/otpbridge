"""
Endpoint interno chamado pelo AGI do Asterisk quando SMS chega via chan_dongle.
Adicionar no main.py: app.include_router(e303_router)
"""
from fastapi import APIRouter, Request
from modems.pool import get_pool

e303_router = APIRouter()


@e303_router.post("/e303/sms")
async def e303_sms(request: Request):
    data = await request.json()
    dongle_name = data.get("dongle_name", "")
    text        = data.get("text", "")
    from_number = data.get("from_number", "")
    print(f"[E303 Webhook] dongle={dongle_name} de={from_number} texto={text}")

    pool = get_pool()
    worker = pool.find_by_dongle(dongle_name)
    if worker:
        worker.deliver_sms(text)
    return {"status": "ok"}
