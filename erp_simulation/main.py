"""Tek komutla çalıştırılabilir simülasyon giriş noktası."""

import sys
import os
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from erp_adapter import app

if __name__ == "__main__":
    uvicorn.run("erp_adapter:app", host="0.0.0.0", port=8000, reload=False)
