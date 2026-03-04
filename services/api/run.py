"""Run migrations/seed then start server."""
import asyncio
import uvicorn
from app.db.init_db import main as init_db

if __name__ == "__main__":
    asyncio.run(init_db())
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
