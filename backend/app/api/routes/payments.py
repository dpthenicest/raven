from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.payment import PaymentInitIn, PaymentInitOut, PaymentVerifyOut
from app.services.payment import CREDIT_PACKS, initialize_payment, verify_payment

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/initialize", response_model=PaymentInitOut)
async def payment_initialize(
    payload: PaymentInitIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Initialize a Monnify payment.
    Amount must be in kobo. Valid amounts: 50000 (₦500), 200000 (₦2,000), 500000 (₦5,000).
    """
    if payload.amount not in CREDIT_PACKS:
        valid = [f"₦{k//100} ({v} credits)" for k, v in CREDIT_PACKS.items()]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid amount. Valid packs: {', '.join(valid)}"
        )

    logger.info(f"Payment init by user {current_user.id}, amount={payload.amount}")
    try:
        result = await initialize_payment(db, current_user, payload.amount)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return PaymentInitOut(**result)


@router.get("/verify/{txn_ref}", response_model=PaymentVerifyOut)
async def payment_verify(
    txn_ref: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Verify a Monnify payment and credit the user if successful."""
    logger.info(f"Payment verification requested: {txn_ref}")
    try:
        txn = await verify_payment(db, txn_ref)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found or already being processed")

    credits_added = CREDIT_PACKS.get(int(txn.amount), 0) if txn.status.value == "SUCCESS" else None
    return PaymentVerifyOut(txn_ref=txn.txn_ref, status=txn.status, credits_added=credits_added)


@router.get("/packs")
async def get_credit_packs():
    """List available credit packs."""
    return [
        {"amount_kobo": amount, "amount_naira": amount // 100, "credits": credits}
        for amount, credits in CREDIT_PACKS.items()
    ]
