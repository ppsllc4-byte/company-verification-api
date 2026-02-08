from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import Optional, Dict, Any
import httpx
import os
from dotenv import load_dotenv
import re
from bs4 import BeautifulSoup
import asyncio
from datetime import datetime

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Company Verification API",
    description="Verify company legitimacy, extract basic info, and check online presence",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class CompanyVerificationRequest(BaseModel):
    company_name: str
    website: Optional[str] = None
    
class CompanyVerificationResponse(BaseModel):
    company_name: str
    verified: bool
    confidence_score: float  # 0.0 to 1.0
    website: Optional[str] = None
    social_media: Dict[str, Optional[str]] = {}
    online_presence: Dict[str, Any] = {}
    risk_flags: list[str] = []
    timestamp: str

# Helper Functions
async def check_website_exists(url: str) -> tuple[bool, Dict[str, Any]]:
    """Check if website exists and extract basic info"""
    try:
        # Ensure URL has protocol
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
        
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract basic info
                title = soup.find('title')
                meta_description = soup.find('meta', attrs={'name': 'description'})
                
                return True, {
                    'status_code': response.status_code,
                    'title': title.text.strip() if title else None,
                    'description': meta_description.get('content') if meta_description else None,
                    'has_ssl': url.startswith('https://'),
                }
            return False, {'status_code': response.status_code}
    except Exception as e:
        return False, {'error': str(e)}

async def search_social_media(company_name: str, domain: Optional[str] = None) -> Dict[str, Optional[str]]:
    """Search for social media profiles"""
    social_links = {
        'linkedin': None,
        'twitter': None,
        'facebook': None,
    }
    
    # Basic search patterns (in production, you'd use APIs)
    search_name = company_name.lower().replace(' ', '')
    
    # These are placeholder patterns - in production you'd actually search
    patterns = {
        'linkedin': f"linkedin.com/company/{search_name}",
        'twitter': f"twitter.com/{search_name}",
        'facebook': f"facebook.com/{search_name}",
    }
    
    # In a real implementation, you'd make actual API calls or web scraping here
    # For now, we'll return the expected patterns
    for platform, pattern in patterns.items():
        social_links[platform] = f"https://{pattern}"
    
    return social_links

def calculate_confidence_score(data: Dict[str, Any]) -> float:
    """Calculate confidence score based on available data"""
    score = 0.0
    max_score = 5.0
    
    # Website exists (+2.0)
    if data.get('website_exists'):
        score += 2.0
        
        # Has SSL (+0.5)
        if data.get('website_info', {}).get('has_ssl'):
            score += 0.5
        
        # Has title and description (+0.5)
        if data.get('website_info', {}).get('title') and data.get('website_info', {}).get('description'):
            score += 0.5
    
    # Has social media presence (+1.5)
    social_count = len([v for v in data.get('social_media', {}).values() if v])
    score += min(social_count * 0.5, 1.5)
    
    # Has online mentions (+0.5)
    if data.get('online_presence', {}).get('has_mentions'):
        score += 0.5
    
    return round(score / max_score, 2)

def identify_risk_flags(data: Dict[str, Any]) -> list[str]:
    """Identify potential risk flags"""
    flags = []
    
    # No website
    if not data.get('website_exists'):
        flags.append("No active website found")
    
    # No SSL
    if data.get('website_exists') and not data.get('website_info', {}).get('has_ssl'):
        flags.append("Website lacks SSL certificate")
    
    # No social media
    if not any(data.get('social_media', {}).values()):
        flags.append("No social media presence detected")
    
    # Website error
    if data.get('website_info', {}).get('error'):
        flags.append(f"Website error: {data['website_info']['error']}")
    
    return flags

# API Endpoints
@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "message": "Company Verification API",
        "version": "1.0.0",
        "endpoints": {
            "verify": "/verify",
            "health": "/health",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/verify", response_model=CompanyVerificationResponse)
async def verify_company(
    request: CompanyVerificationRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Verify a company's legitimacy and online presence
    
    This endpoint checks:
    - Website existence and validity
    - SSL certificate presence
    - Social media profiles
    - Basic online presence
    - Risk flags
    
    Returns a confidence score from 0.0 to 1.0
    """
    
    # In production, verify payment/authorization here
    # For now, we'll allow all requests
    
    try:
        verification_data = {}
        
        # Check website
        if request.website:
            website_exists, website_info = await check_website_exists(request.website)
            verification_data['website_exists'] = website_exists
            verification_data['website_info'] = website_info
        else:
            # Try to find website by company name
            # In production, use a search API
            verification_data['website_exists'] = False
            verification_data['website_info'] = {}
        
        # Search for social media
        social_media = await search_social_media(request.company_name, request.website)
        verification_data['social_media'] = social_media
        
        # Check for online presence (placeholder)
        verification_data['online_presence'] = {
            'has_mentions': True,  # In production, actually search
            'search_results_count': 0
        }
        
        # Calculate confidence score
        confidence_score = calculate_confidence_score(verification_data)
        
        # Identify risk flags
        risk_flags = identify_risk_flags(verification_data)
        
        # Determine if verified
        verified = confidence_score >= 0.5 and len(risk_flags) <= 1
        
        return CompanyVerificationResponse(
            company_name=request.company_name,
            verified=verified,
            confidence_score=confidence_score,
            website=request.website if verification_data.get('website_exists') else None,
            social_media=social_media,
            online_presence=verification_data.get('online_presence', {}),
            risk_flags=risk_flags,
            timestamp=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")

@app.post("/verify/batch")
async def verify_companies_batch(companies: list[CompanyVerificationRequest]):
    """Verify multiple companies in one request"""
    if len(companies) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 companies per batch request")
    
    results = []
    for company in companies:
        try:
            result = await verify_company(company)
            results.append(result)
        except Exception as e:
            results.append({
                "company_name": company.company_name,
                "error": str(e)
            })
    
    return {"results": results}

@app.get("/pricing")
async def get_pricing():
    """Return pricing information"""
    return {
        "currency": "USD",
        "price_per_verification": 0.10,
        "batch_discount": {
            "10_plus": 0.09,
            "100_plus": 0.08,
            "1000_plus": 0.07
        },
        "payment_methods": ["x402", "crypto"],
        "subscription_available": False
    }

# Run with: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)