from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
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
    logger.info(f"Payment init by user {current_user.id}, amount={payload.amount}")
    result = await initialize_payment(db, current_user, payload.amount)
    logger.info(f"Payment initialized: txn_ref={result['txn_ref']}")
    return PaymentInitOut(**result)


@router.get("/verify/{txn_ref}", response_model=PaymentVerifyOut)
async def payment_verify(
    txn_ref: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    logger.info(f"Payment verification requested: {txn_ref}")
    txn = await verify_payment(db, txn_ref)
    if not txn:
        logger.warning(f"Transaction not found: {txn_ref}")
        raise HTTPException(status_code=404, detail="Transaction not found")
    logger.info(f"Transaction {txn_ref} status: {txn.status}")
    return PaymentVerifyOut(txn_ref=txn.txn_ref, status=txn.status)
