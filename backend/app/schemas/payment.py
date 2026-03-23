import uuid
from typing import Optional

from pydantic import BaseModel

from app.models.transaction import TransactionStatus


class PaymentInitIn(BaseModel):
    amount: float  # in kobo


class PaymentInitOut(BaseModel):
    txn_ref: str
    payment_url: str


class PaymentVerifyOut(BaseModel):
    txn_ref: str
    status: TransactionStatus
    credits_added: Optional[int] = None
