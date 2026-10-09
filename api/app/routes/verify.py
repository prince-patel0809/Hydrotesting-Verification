from fastapi import APIRouter, Request

from app.db import Database
from app.schemas import VerifyRequest, VerifyResponse
from app.services.hydrotest_verification import verify_registered_plate

router = APIRouter(prefix="/api")


@router.post("/verify", response_model=VerifyResponse)
def verify_hydrotest(payload: VerifyRequest, request: Request) -> VerifyResponse:
    database: Database = request.app.state.hydrotest_db
    result = verify_registered_plate(database, payload.plate)
    return VerifyResponse.model_validate(result)
