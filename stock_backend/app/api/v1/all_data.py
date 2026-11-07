"""Manual remote workspace and administrator quota settings."""
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.api.deps import get_current_admin
from app.core.config import get_settings
from app.core.response import ok

router = APIRouter(prefix='/api/v1', tags=['全数据'])

def bridge(path, payload):
    try:
        response = httpx.post(get_settings().STOCKDB_SDK_URL.rstrip('/') + path, json=payload, timeout=180)
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, '在线查询桥暂不可用') from exc
    if response.status_code != 200:
        raise HTTPException(response.status_code, body.get('detail', '在线查询失败'), headers={'Retry-After': str(body.get('retry_after', 30))})
    return ok(data=body)

@router.post('/all-data/query')
def query(payload: dict):
    return bridge('/online/query', payload)

@router.get('/all-data/status')
def status():
    return bridge('/online/policy', {})

class Policy(BaseModel):
    interval_seconds: int = Field(ge=30, le=86400)

@router.put('/admin/online-data-policy')
def save_policy(payload: Policy, admin=Depends(get_current_admin)):
    return bridge('/online/policy', payload.model_dump())
