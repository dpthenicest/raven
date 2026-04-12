import uuid
from typing import Optional

from pydantic import BaseModel

from app.models.transaction import TransactionStatus


class PaymentInitIn(BaseModel):
    amount: int  # in kobo (e.g. 50000 = ₦500)


class PaymentInitOut(BaseModel):
    txn_ref: str
    payment_url: str


class PaymentVerifyOut(BaseModel):
    txn_ref: str
    status: TransactionStatus
    credits_added: Optional[int] = None
