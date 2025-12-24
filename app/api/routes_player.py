# app/api/routes_player.py
from fastapi import APIRouter, Request, HTTPException

router = APIRouter(prefix="/player", tags=["player"])


def get_executor(request: Request):
    executor = getattr(request.app.state, "executor", None)
    if executor is None:
        raise HTTPException(status_code=500, detail="Executor não inicializado")
    return executor


# =====================================================
# PLAY STEP (por índice)
# =====================================================
@router.post("/play/{index}")
async def play(index: int, request: Request):
    executor = get_executor(request)
    await executor.play(index)
    return {"ok": True}


# =====================================================
# PAUSE
# =====================================================
@router.post("/pause")
async def pause(request: Request):
    executor = get_executor(request)
    await executor.pause()
    return {"ok": True}


# =====================================================
# RESUME
# 👉 como o executor não tem resume explícito,
#    resume = play no índice atual
# =====================================================
@router.post("/resume")
async def resume(request: Request):
    executor = get_executor(request)

    if executor.current_index < 0:
        raise HTTPException(status_code=400, detail="Nenhum step ativo para retomar")

    await executor.play(executor.current_index)
    return {"ok": True}


# =====================================================
# STOP
# 👉 stop = pause + reset de estado local
# =====================================================
@router.post("/stop")
async def stop(request: Request):
    executor = get_executor(request)

    await executor.pause()
    executor.current_index = -1

    return {"ok": True}


# =====================================================
# SKIP / NEXT
# =====================================================
@router.post("/skip")
async def skip(request: Request):
    executor = get_executor(request)
    await executor.next()
    return {"ok": True}