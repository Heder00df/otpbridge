"""
Webhook que o GoIP chama quando um SMS chega.
Adicionar no main.py: app.include_router(goip_router)

Configurar no painel GoIP:
  SMS → Receive URL: http://seuservidor:8000/goip/sms
"""
from fastapi import APIRouter, Request
from modems.pool import get_pool

goip_router = APIRouter()

@goip_router.post("/goip/sms")
async def goip_sms(request: Request):
    data = await request.form()
    line = int(data.get("line", 1))
    text = data.get("msg", "")
    src  = data.get("src_num", "")
    print(f"[GoIP Webhook] linha={line} de={src} texto={text}")

    pool = get_pool()
    worker = pool.find_by_line("goip", line)
    if worker:
        worker.deliver_sms(text)
    return {"status": "ok"}
