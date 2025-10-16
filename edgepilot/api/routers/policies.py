# edgepilot/api/routers/policies.py
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any
from ...scheduler import get_scheduler

router = APIRouter()


class PolicySetBody(BaseModel):
    name: str
    rules: Dict[str, Any]


@router.post("/set")
def policy_set(body: PolicySetBody):
    sch = get_scheduler()
    return {"active": sch.policy_set(body.name, body.rules)}


@router.get("/simulate")
def simulate():
    sch = get_scheduler()
    return sch.simulate()
