from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()


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
