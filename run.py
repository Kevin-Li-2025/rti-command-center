#!/usr/bin/env python3
"""start the RTI server."""
import uvicorn
from rti.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "rti.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
