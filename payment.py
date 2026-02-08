import stripe
import os
from dotenv import load_dotenv
from typing import Optional, Dict, Any
from fastapi import HTTPException
from api_keys import api_key_manager

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
PRICE_PER_VERIFICATION = float(os.getenv("PRICE_PER_VERIFICATION", "0.10"))

class PaymentProcessor:
    @staticmethod
    async def create_checkout_session(success_url: str, cancel_url: str, quantity: int = 1) -> Dict[str, Any]:
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': 'Company Verification API Credits',
                            'description': 'Credits for company verification operations'
                        },
                        'unit_amount': int(PRICE_PER_VERIFICATION * 100)
                    },
                    'quantity': quantity
                }],
                mode='payment',
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={'credits': quantity}
            )
            return {'session_id': session.id, 'url': session.url, 'amount_total': session.amount_total / 100 if session.amount_total else 0}
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Checkout error: {str(e)}")

async def verify_payment_token(authorization: Optional[str], cost_in_credits: int = 1) -> bool:
    print(f"DEBUG Auth: {authorization}")
    if not authorization or not authorization.startswith("Bearer "):
        return False
    api_key = authorization.replace("Bearer ", "").strip()
    print(f"DEBUG Key: {api_key[:15]}")
    key_data = api_key_manager.validate_key(api_key)
    print(f"DEBUG Valid: {key_data is not None}")
    if not key_data:
        return False
    result = api_key_manager.deduct_credits(api_key, cost_in_credits)
    print(f"DEBUG Deduct: {result}")
    return result
