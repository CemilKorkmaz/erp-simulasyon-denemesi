"""Tek komutla çalıştırılabilir simülasyon giriş noktası."""

import uvicorn
from erp_adapter import app

if __name__ == "__main__":
    uvicorn.run("erp_adapter:app", host="0.0.0.0", port=8000, reload=False)
