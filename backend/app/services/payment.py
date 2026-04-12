"""Payment service — Monnify integration with race condition protection."""
import hashlib
import hmac
import uuid
from typing import Optional

import httpx
from loguru import logger
from sqlalchemy import select, update
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


def _monnify_auth_header() -> str:
    """Base64-encode Monnify API key and secret for Basic Auth."""
    import base64
    credentials = f"{settings.MONNIFY_API_KEY}:{settings.MONNIFY_SECRET_KEY}"
    return "Basic " + base64.b64encode(credentials.encode()).decode()


async def _get_monnify_token() -> Optional[str]:
    """Obtain a Monnify access token."""
    url = f"{settings.MONNIFY_BASE_URL}/api/v1/auth/login"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, headers={"Authorization": _monnify_auth_header()})
        if resp.status_code != 200:
            logger.error(f"Monnify auth failed: {resp.text}")
            return None
        data = resp.json()
        return data.get("responseBody", {}).get("accessToken")


async def initialize_payment(db: AsyncSession, user: User, amount: int) -> dict:
    """
    Initialize a Monnify payment.
    amount is in kobo (e.g. 50000 = ₦500).
    """
    txn_ref = f"RVN-{uuid.uuid4().hex[:12].upper()}"
    amount_naira = amount / 100  # Monnify uses naira, not kobo

    logger.info(f"Initializing Monnify payment: user={user.id}, amount={amount}, ref={txn_ref}")

    token = await _get_monnify_token()
    if not token:
        raise RuntimeError("Could not obtain Monnify access token")

    payload = {
        "amount": amount_naira,
        "customerName": user.name or user.email,
        "customerEmail": user.email,
        "paymentReference": txn_ref,
        "paymentDescription": "Project Raven Credits",
        "currencyCode": "NGN",
        "contractCode": settings.MONNIFY_CONTRACT_CODE,
        "redirectUrl": settings.MONNIFY_REDIRECT_URL,
        "paymentMethods": ["CARD", "ACCOUNT_TRANSFER"],
    }

    url = f"{settings.MONNIFY_BASE_URL}/api/v1/merchant/transactions/init-transaction"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

    if resp.status_code != 200:
        logger.error(f"Monnify init failed: {resp.text}")
        raise RuntimeError(f"Monnify payment initialization failed: {resp.text}")

    data = resp.json().get("responseBody", {})
    checkout_url = data.get("checkoutUrl", "")

    # Persist transaction as PENDING
    txn = Transaction(
        user_id=user.id,
        txn_ref=txn_ref,
        amount=amount,
        status=TransactionStatus.PENDING,
    )
    db.add(txn)
    await db.commit()

    logger.info(f"Payment initialized: ref={txn_ref}, checkout_url={checkout_url}")
    return {"txn_ref": txn_ref, "payment_url": checkout_url}


async def verify_payment(db: AsyncSession, txn_ref: str) -> Optional[Transaction]:
    """
    Verify a Monnify payment and credit the user.

    Uses SELECT FOR UPDATE to prevent race conditions — only one request
    can process a given transaction at a time.
    """
    logger.info(f"Verifying payment: {txn_ref}")

    # Lock the transaction row to prevent concurrent processing
    result = await db.execute(
        select(Transaction)
        .where(Transaction.txn_ref == txn_ref)
        .with_for_update(skip_locked=True)
    )
    txn = result.scalar_one_or_none()

    if not txn:
        logger.warning(f"Transaction {txn_ref} not found or already being processed")
        return None

    if txn.status != TransactionStatus.PENDING:
        logger.info(f"Transaction {txn_ref} already processed: {txn.status}")
        return txn

    # Verify with Monnify
    token = await _get_monnify_token()
    if not token:
        raise RuntimeError("Could not obtain Monnify access token")

    encoded_ref = txn_ref.replace("/", "%2F")
    url = f"{settings.MONNIFY_BASE_URL}/api/v1/merchant/transactions/query?paymentReference={encoded_ref}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})

    if resp.status_code != 200:
        logger.error(f"Monnify verify failed: {resp.text}")
        txn.status = TransactionStatus.FAILED
        await db.commit()
        return txn

    body = resp.json().get("responseBody", {})
    payment_status = body.get("paymentStatus", "")

    if payment_status != "PAID":
        logger.warning(f"Payment {txn_ref} not paid: {payment_status}")
        txn.status = TransactionStatus.FAILED
        await db.commit()
        return txn

    # Payment confirmed — credit the user atomically
    credits = CREDIT_PACKS.get(int(txn.amount), 0)
    txn.status = TransactionStatus.SUCCESS

    if credits:
        # Atomic increment to prevent race conditions on credits
        await db.execute(
            update(User)
            .where(User.id == txn.user_id)
            .values(credits=User.credits + credits)
        )
        logger.info(f"Credits added: user={txn.user_id}, credits={credits}")

    await db.commit()
    await db.refresh(txn)
    return txn
