from fastapi import APIRouter, Request, Query, HTTPException
from config import SUPPLIER_KEY

router = APIRouter()

def verify_key(key: str):
    if key != SUPPLIER_KEY:
        raise HTTPException(status_code=403, detail="Invalid key")

@router.get("/supplier")
async def supplier(
    request: Request,
    action: str = Query(...),
    key: str = Query(...),
    service: str = Query(None),
    country: str = Query(None),
    activationId: str = Query(None),
    status: str = Query(None),
):
    verify_key(key)
    pool = request.app.state.modem_pool

    if action == "GET_SERVICES":
        return pool.get_services()

    if action == "GET_NUMBER":
        if not service:
            raise HTTPException(status_code=400, detail="service required")
        result = pool.reserve_modem(service, country)
        if result is None:
            return {"status": "no_number"}
        return {"status": "success", "number": result["number"], "activationId": result["activation_id"]}

    if action == "FINISH_ACTIVATION":
        if not activationId or not status:
            raise HTTPException(status_code=400, detail="activationId and status required")
        pool.finish_activation(activationId, int(status))
        return {"status": "success"}

    raise HTTPException(status_code=400, detail=f"Unknown action: {action}")
