import uuid
from typing import Optional

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User

# Credit packs: amount in kobo -> credits
CREDIT_PACKS = {
    50000: 5,    # ₦500
    200000: 25,  # ₦2,000
    500000: 80,  # ₦5,000
}


async def initialize_payment(db: AsyncSession, user: User, amount: float) -> dict:
    txn_ref = f"RVN-{uuid.uuid4().hex[:12].upper()}"
    logger.info(f"Initializing payment: user={user.id}, amount={amount}, ref={txn_ref}")
    txn = Transaction(user_id=user.id, txn_ref=txn_ref, amount=amount)
    db.add(txn)
    await db.commit()
    payment_url = f"{settings.INTERSWITCH_BASE_URL}/pay?ref={txn_ref}&amount={int(amount)}"
    return {"txn_ref": txn_ref, "payment_url": payment_url}


async def verify_payment(db: AsyncSession, txn_ref: str) -> Optional[Transaction]:
    logger.info(f"Verifying payment: {txn_ref}")
    result = await db.execute(select(Transaction).where(Transaction.txn_ref == txn_ref))
    txn = result.scalar_one_or_none()
    if not txn or txn.status != TransactionStatus.PENDING:
        logger.warning(f"Transaction {txn_ref} not pending or not found")
        return txn

    txn.status = TransactionStatus.SUCCESS
    credits = CREDIT_PACKS.get(int(txn.amount), 0)

    user_result = await db.execute(select(User).where(User.id == txn.user_id))
    user = user_result.scalar_one_or_none()
    if user and credits:
        user.credits += credits
        logger.info(f"Credits added: user={user.id}, credits={credits}, new_total={user.credits}")

    await db.commit()
    return txn
