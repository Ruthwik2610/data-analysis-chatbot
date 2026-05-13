import io
import json
import pandas as pd
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/journeys", tags=["Travel"])

class CreateJourneyRequest(BaseModel):
    chat_id: str | None = None
    intent: dict[str, Any]
    offer: dict[str, Any]

@router.post("")
def save_journey(req: CreateJourneyRequest, request: Request):
    from backend.server import DB, _current_user_id
    user_id = _current_user_id(request)
    journey = DB.create_travel_journey(
        owner_id=user_id,
        chat_id=req.chat_id,
        intent=req.intent,
        offer=req.offer
    )
    return journey

@router.get("/export")
def export_journeys(request: Request):
    from backend.server import DB, _current_user_id
    user_id = _current_user_id(request)
    journeys = DB.list_travel_journeys(owner_id=user_id)
    
    if not journeys:
        raise HTTPException(status_code=404, detail="No journeys found")
        
    df = pd.DataFrame(journeys)
    if "flight_offer_json" in df.columns:
        df["flight_offer"] = df["flight_offer_json"].apply(lambda x: json.loads(x) if x else {})
        df["airline"] = df["flight_offer"].apply(lambda x: x.get("airline") if isinstance(x, dict) else None)
        df["price_usd"] = df["flight_offer"].apply(lambda x: x.get("price_usd") if isinstance(x, dict) else None)
        df = df.drop(columns=["flight_offer_json", "flight_offer"])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Journeys")
    
    output.seek(0)
    return StreamingResponse(
        output, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=travel_journeys.xlsx"}
    )
