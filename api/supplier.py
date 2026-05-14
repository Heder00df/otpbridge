from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from config import SUPPLIER_KEY

router = APIRouter()

_OPERATOR = "any"       # nossos chips são "any" operadora
_COUNTRY  = "brazil"    # país dos nossos chips


def verify_key(key: str):
    if key != SUPPLIER_KEY:
        raise HTTPException(status_code=403, detail="Invalid key")


@router.post("/supplier")
async def supplier(request: Request):
    body = await request.json()
    key    = body.get("key", "")
    action = body.get("action", "")
    verify_key(key)

    pool = request.app.state.modem_pool

    # ── 1. GET_COUNT ────────────────────────────────────────
    if action == "GET_COUNT":
        free = _count_free(pool)
        count_map = {
            _COUNTRY: {
                _OPERATOR: {
                    code: {"SMS": free}
                    for code in _service_codes()
                }
            }
        }
        return {"status": "SUCCESS", "countMap": count_map}

    # ── 2. GET_NUMBER ────────────────────────────────────────
    if action == "GET_NUMBER":
        service  = body.get("service", "")
        country  = body.get("country", _COUNTRY)
        operator = body.get("operator", _OPERATOR)
        exception_set = body.get("exceptionPhoneSet", [])

        if not service:
            return JSONResponse({"status": "ERROR", "error": "service required"})

        result = pool.reserve_modem(service, country, exception_set)
        if result is None:
            return {"status": "NO_NUMBERS"}

        return {
            "status":       "SUCCESS",
            "number":       int(result["number"]),
            "activationId": int(result["activation_id"]),
            "supported":    ["SMS"],
        }

    # ── 3. FINISH_ACTIVATION ─────────────────────────────────
    if action == "FINISH_ACTIVATION":
        activation_id = body.get("activationId")
        status        = body.get("status")
        if activation_id is None or status is None:
            return JSONResponse({"status": "ERROR", "error": "activationId and status required"})

        result = pool.finish_activation(str(activation_id), int(status))
        if result == "NOT_FOUND":
            # Idempotência: se não achar, retorna SUCCESS mesmo assim
            return {"status": "SUCCESS"}
        return {"status": "SUCCESS"}

    return JSONResponse({"status": "ERROR", "error": f"Unknown action: {action}"})


def _count_free(pool) -> int:
    if not pool:
        return 0
    with pool.lock:
        return sum(1 for m in pool.modems.values() if m.is_free()
                   and not m.number.startswith("unknown"))


def _service_codes() -> list[str]:
    import json
    from pathlib import Path
    path = Path(__file__).parent.parent / "services.json"
    return [s["code"] for s in json.loads(path.read_text())]
