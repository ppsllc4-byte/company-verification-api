from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
import os
from dotenv import load_dotenv
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from payment import PaymentProcessor, verify_payment_token
from api_keys import api_key_manager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

load_dotenv()
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

# Initialize Sentry
sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    integrations=[FastApiIntegration()],
    traces_sample_rate=0.1,
    environment="production"
)
app = FastAPI(
    title="Company Verification API",
    description="Verify business legitimacy and online presence",
    version="2.0.0"
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CompanyVerifyRequest(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    website: Optional[str] = Field(None, max_length=500)
    
    @validator('website')
    def validate_website(cls, v):
        if v and not (v.startswith('http://') or v.startswith('https://')):
            v = f"https://{v}"
        return v

class BatchVerifyRequest(BaseModel):
    companies: List[CompanyVerifyRequest] = Field(..., max_items=10)

@app.get("/")
@limiter.limit("100/minute")
async def root(request: Request):
    return {
        "message": "Company Verification API",
        "version": "2.0.0",
        "security": "API key authentication + rate limiting enabled",
        "endpoints": {
            "verify": "POST /verify",
            "batch": "POST /verify/batch",
            "health": "GET /health",
            "credits": "GET /credits/check",
            "purchase": "POST /purchase"
        }
    }

@app.get("/health")
@limiter.limit("100/minute")
async def health_check(request: Request):
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0",
        "security": "enabled"
    }
@app.get("/.well-known/x402")
async def x402_discovery(request: Request):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=402,
        content={
            "version": "1.0.0",
            "accepts": ["stripe"],
            "price": {
                "amount": "0.10",
                "currency": "USD"
            },
            "purchase_url": 
"https://company-verification-api-production.up.railway.app/purchase"
        }
    )

async def verify_company_internal(company_name: str, website: Optional[str]) -> Dict[str, Any]:
    result = {
        "company_name": company_name,
        "website": website,
        "verification_status": "pending",
        "confidence_score": 0.0,
        "checks": {
            "website_exists": False,
            "ssl_valid": False,
            "social_media": {}
        },
        "risk_flags": [],
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if not website:
        result["verification_status"] = "incomplete"
        result["risk_flags"].append("No website provided")
        return result
    
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(website)
            
            if response.status_code == 200:
                result["checks"]["website_exists"] = True
                result["confidence_score"] += 0.4
                
                if website.startswith('https://'):
                    result["checks"]["ssl_valid"] = True
                    result["confidence_score"] += 0.2
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                social_links = {
                    'linkedin': soup.find('a', href=lambda x: x and 'linkedin.com' in x),
                    'twitter': soup.find('a', href=lambda x: x and ('twitter.com' in x or 'x.com' in x)),
                    'facebook': soup.find('a', href=lambda x: x and 'facebook.com' in x)
                }
                
                for platform, link in social_links.items():
                    if link:
                        result["checks"]["social_media"][platform] = link.get('href')
                        result["confidence_score"] += 0.1
                
                result["verification_status"] = "verified"
                
                if result["confidence_score"] < 0.5:
                    result["risk_flags"].append("Low online presence")
                if not result["checks"]["ssl_valid"]:
                    result["risk_flags"].append("No SSL certificate")
            else:
                result["risk_flags"].append(f"Website returned status {response.status_code}")
    except httpx.TimeoutException:
        result["risk_flags"].append("Website timeout")
    except Exception as e:
        result["risk_flags"].append(f"Verification error: {str(e)}")
    
    result["confidence_score"] = min(1.0, result["confidence_score"])
    return result

@app.post("/verify")
@limiter.limit("60/minute")
async def verify_company(
    request: Request,
    company: CompanyVerifyRequest,
    authorization: Optional[str] = Header(None)
):
    is_authorized = await verify_payment_token(authorization, cost_in_credits=10)
    
    if not is_authorized:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Payment required",
                "message": "Invalid API key or insufficient credits",
                "pricing": "$0.10 per verification (10 credits)",
                "get_credits": "/purchase"
            }
        )
    
    try:
        result = await verify_company_internal(company.company_name, company.website)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")

@app.post("/verify/batch")
@limiter.limit("10/minute")
async def verify_batch(
    request: Request,
    batch: BatchVerifyRequest,
    authorization: Optional[str] = Header(None)
):
    credits_needed = len(batch.companies) * 10
    is_authorized = await verify_payment_token(authorization, cost_in_credits=credits_needed)
    
    if not is_authorized:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Payment required",
                "message": f"Insufficient credits. Need {credits_needed} credits",
                "get_credits": "/purchase"
            }
        )
    
    results = []
    for company in batch.companies:
        result = await verify_company_internal(company.company_name, company.website)
        results.append(result)
    
    return {"status": "success", "total_verified": len(results), "results": results}

@app.get("/credits/check")
@limiter.limit("100/minute")
async def check_credits(request: Request, authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    api_key = authorization.replace("Bearer ", "").strip()
    credits = api_key_manager.get_credits(api_key)
    if credits is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return {
        "credits_remaining": credits,
        "verifications_available": credits // 10,
        "status": "active" if credits >= 10 else "low_credits"
    }

@app.post("/admin/create-api-key")
async def create_api_key(
    user_email: str,
    credits: int = 100,
    admin_secret: str = Header(None, alias="X-Admin-Secret")
):
    if admin_secret != os.getenv("API_SECRET_KEY"):
        raise HTTPException(status_code=403, detail="Forbidden")
    api_key = api_key_manager.create_key(user_email, credits)
    return {
        "status": "success",
        "api_key": api_key,
        "user_email": user_email,
        "credits": credits,
        "verifications": credits // 10,
        "message": "SAVE THIS KEY!"
    }

@app.post("/purchase")
@limiter.limit("10/minute")
async def purchase_credits(request: Request, credits: int = 100, email: Optional[str] = None):
    if credits < 10 or credits > 10000:
        raise HTTPException(status_code=400, detail="Credits must be between 10 and 10,000")
    base_url = os.getenv("BASE_URL", "https://company-verification-api-production.up.railway.app")
    session = await PaymentProcessor.create_checkout_session(
        success_url=f"{base_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base_url}/payment/cancel",
        quantity=credits
    )
    return {
        "checkout_url": session['url'],
        "session_id": session['session_id'],
        "total_amount": session['amount_total'],
        "credits": credits,
        "verifications": credits // 10
    }

@app.get("/payment/success")
async def payment_success(session_id: str):
    try:
        payment_info = await PaymentProcessor.verify_session(session_id)
        user_email = payment_info['customer_email'] or f"user_{session_id[:8]}@stripe.customer"
        credits = payment_info['credits']
        api_key = api_key_manager.create_key(user_email, credits)
        
        return {
            "status": "success",
            "message": "SAVE THIS API KEY! It will not be shown again.",
            "api_key": api_key,
            "credits": credits,
            "verifications_available": credits // 10,
            "user_email": user_email,
            "amount_paid": f"${payment_info['amount_total']:.2f}",
            "instructions": {
                "step_1": "Copy the api_key above",
                "step_2": "Use it in Authorization header",
                "example": f"Authorization: Bearer {api_key}"
            },
            "docs": "https://company-verification-api-production.up.railway.app/docs"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Payment processing failed: {str(e)}")

@app.get("/payment/cancel")
async def payment_cancel():
    return {"status": "cancelled", "message": "Payment cancelled"}

@app.get("/pricing")
@limiter.limit("100/minute")
async def get_pricing(request: Request):
    return {
        "single_verification": "$0.10 (10 credits)",
        "batch_verification": "$0.10 per company",
        "bulk_pricing": {
            "100_credits": "$1.00",
            "1000_credits": "$10.00",
            "10000_credits": "$100.00"
        }
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
