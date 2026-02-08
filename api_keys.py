import json
import os
import hashlib
import secrets
from datetime import datetime
from typing import Optional, Dict

API_KEYS_FILE = "api_keys_db.json"

class APIKeyManager:
    def __init__(self):
        self.db_file = API_KEYS_FILE
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        if not os.path.exists(self.db_file):
            with open(self.db_file, 'w') as f:
                json.dump({"keys": {}}, f, indent=2)
    
    def _read_db(self) -> Dict:
        with open(self.db_file, 'r') as f:
            return json.load(f)
    
    def _write_db(self, data: Dict):
        with open(self.db_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    @staticmethod
    def generate_key() -> str:
        return f"cvapi_{secrets.token_urlsafe(32)}"
    
    @staticmethod
    def hash_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    def create_key(self, user_email: str, credits: int) -> str:
        db = self._read_db()
        api_key = self.generate_key()
        key_hash = self.hash_key(api_key)
        
        db["keys"][key_hash] = {
            "user_email": user_email,
            "credits_remaining": credits,
            "created_at": datetime.utcnow().isoformat(),
            "last_used": None,
            "is_active": True
        }
        
        self._write_db(db)
        return api_key
    
    def validate_key(self, api_key: str) -> Optional[Dict]:
        db = self._read_db()
        key_hash = self.hash_key(api_key)
        key_data = db["keys"].get(key_hash)
        
        if not key_data or not key_data["is_active"]:
            return None
        return key_data
    
    def deduct_credits(self, api_key: str, amount: int) -> bool:
        db = self._read_db()
        key_hash = self.hash_key(api_key)
        key_data = db["keys"].get(key_hash)
        
        if not key_data or not key_data["is_active"]:
            return False
        if key_data["credits_remaining"] < amount:
            return False
        
        key_data["credits_remaining"] -= amount
        key_data["last_used"] = datetime.utcnow().isoformat()
        self._write_db(db)
        return True
    
    def get_credits(self, api_key: str) -> Optional[int]:
        key_data = self.validate_key(api_key)
        return key_data["credits_remaining"] if key_data else None

api_key_manager = APIKeyManager()
