from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import JSONResponse
from config import SUPPLIER_KEY

router = APIRouter()

_OPERATOR = "any"
_COUNTRY  = "brazil"


def verify_key(key: str):
    if key != SUPPLIER_KEY:
        raise HTTPException(status_code=403, detail="Invalid key")


async def _get_params(request: Request) -> dict:
    """Aceita tanto POST JSON quanto GET query params."""
    if request.method == "POST":
        try:
            return await request.json()
        except Exception:
            return {}
    else:
        return dict(request.query_params)


async def _handle(request: Request):
    params = await _get_params(request)
    key    = params.get("key", "")
    action = params.get("action", "")
    verify_key(key)

    pool = request.app.state.modem_pool

    # ── GET_SERVICES (formato antigo HeroSMS) ────────────────
    if action == "GET_SERVICES":
        free = _count_free(pool)
        return {"status": "success", "services": {code: free for code in _service_codes()}}

    # ── GET_COUNT ─────────────────────────────────────────────
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

    # ── GET_NUMBER ────────────────────────────────────────────
    if action == "GET_NUMBER":
        service       = params.get("service", "")
        country       = params.get("country", _COUNTRY)
        exception_set = params.get("exceptionPhoneSet", [])
        if isinstance(exception_set, str):
            exception_set = [exception_set]

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

    # ── FINISH_ACTIVATION ─────────────────────────────────────
    if action == "FINISH_ACTIVATION":
        activation_id = params.get("activationId")
        status        = params.get("status")
        if activation_id is None or status is None:
            return JSONResponse({"status": "ERROR", "error": "activationId and status required"})

        result = pool.finish_activation(str(activation_id), int(status))
        return {"status": "SUCCESS"}

    return JSONResponse({"status": "ERROR", "error": f"Unknown action: {action}"})


@router.post("/supplier")
async def supplier_post(request: Request):
    return await _handle(request)


@router.get("/supplier")
async def supplier_get(request: Request):
    return await _handle(request)


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
