from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.payment import PaymentInitIn, PaymentInitOut, PaymentVerifyOut
from app.services.payment import initialize_payment, verify_payment

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/initialize", response_model=PaymentInitOut)
async def payment_initialize(
    payload: PaymentInitIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await initialize_payment(db, current_user, payload.amount)
    return PaymentInitOut(**result)


@router.get("/verify/{txn_ref}", response_model=PaymentVerifyOut)
async def payment_verify(
    txn_ref: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    txn = await verify_payment(db, txn_ref)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return PaymentVerifyOut(txn_ref=txn.txn_ref, status=txn.status)
