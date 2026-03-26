"""
Session store para o pipeline multi-agente.

Substitui o dict em memória por Redis com:
- TTL automático (sessões expiram após inatividade)
- Autenticação por user_id (impede acesso cross-user)
- Cleanup automático (sem vazamento de memória)

Fallback para dict em memória quando Redis não está disponível.
"""
import json
import logging
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

SESSION_TTL = 3600  # 1 hora
SESSION_PREFIX = "pipeline_session:"

# Redis connection (lazy init)
_redis = None
_redis_available: Optional[bool] = None

# Fallback in-memory store (dev only)
_memory_store: dict[str, dict] = {}
_memory_owners: dict[str, str] = {}


async def _get_redis():
    """Lazy Redis connection with availability check."""
    global _redis, _redis_available
    if _redis_available is False:
        return None
    if _redis is not None:
        return _redis
    try:
        from app.core.config import settings
        from redis.asyncio import Redis
        _redis = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
        )
        await _redis.ping()
        _redis_available = True
        logger.info("Redis session store connected: %s", settings.REDIS_URL)
        return _redis
    except Exception as e:
        _redis_available = False
        logger.warning("Redis unavailable, using in-memory session store: %s", e)
        return None


async def create_session(user_id: str, data: dict) -> str:
    """Create a new session with TTL. Returns session_id."""
    session_id = str(uuid.uuid4())
    payload = {
        "user_id": user_id,
        "created_at": datetime.utcnow().isoformat(),
        "last_active": datetime.utcnow().isoformat(),
        **data,
    }

    redis = await _get_redis()
    if redis:
        key = f"{SESSION_PREFIX}{session_id}"
        await redis.set(key, json.dumps(payload, default=str), ex=SESSION_TTL)
    else:
        _memory_store[session_id] = payload
        _memory_owners[session_id] = user_id
        # Cleanup old sessions (keep max 100)
        if len(_memory_store) > 100:
            oldest = sorted(_memory_store, key=lambda k: _memory_store[k].get("last_active", ""))
            for old_id in oldest[:len(_memory_store) - 100]:
                _memory_store.pop(old_id, None)
                _memory_owners.pop(old_id, None)

    return session_id


async def get_session(session_id: str, user_id: str) -> Optional[dict]:
    """Get session data. Returns None if not found or unauthorized."""
    redis = await _get_redis()
    if redis:
        key = f"{SESSION_PREFIX}{session_id}"
        raw = await redis.get(key)
        if raw is None:
            return None
        data = json.loads(raw)
        if data.get("user_id") != user_id:
            logger.warning(
                "Session access denied: session=%s requested_by=%s owner=%s",
                session_id, user_id, data.get("user_id"),
            )
            return None
        # Refresh TTL (sliding window)
        await redis.expire(key, SESSION_TTL)
        data["last_active"] = datetime.utcnow().isoformat()
        await redis.set(key, json.dumps(data, default=str), ex=SESSION_TTL)
        return data
    else:
        data = _memory_store.get(session_id)
        if data is None:
            return None
        owner = _memory_owners.get(session_id)
        if owner != user_id:
            logger.warning(
                "Session access denied: session=%s requested_by=%s owner=%s",
                session_id, user_id, owner,
            )
            return None
        data["last_active"] = datetime.utcnow().isoformat()
        return data


async def update_session(session_id: str, user_id: str, updates: dict) -> bool:
    """Update session data. Returns False if not found or unauthorized."""
    data = await get_session(session_id, user_id)
    if data is None:
        return False

    data.update(updates)
    data["last_active"] = datetime.utcnow().isoformat()

    redis = await _get_redis()
    if redis:
        key = f"{SESSION_PREFIX}{session_id}"
        await redis.set(key, json.dumps(data, default=str), ex=SESSION_TTL)
    else:
        _memory_store[session_id] = data

    return True


async def delete_session(session_id: str, user_id: str) -> bool:
    """Delete a session. Returns False if not found or unauthorized."""
    redis = await _get_redis()
    if redis:
        key = f"{SESSION_PREFIX}{session_id}"
        raw = await redis.get(key)
        if raw:
            data = json.loads(raw)
            if data.get("user_id") != user_id:
                return False
        await redis.delete(key)
    else:
        owner = _memory_owners.get(session_id)
        if owner and owner != user_id:
            return False
        _memory_store.pop(session_id, None)
        _memory_owners.pop(session_id, None)
    return True
