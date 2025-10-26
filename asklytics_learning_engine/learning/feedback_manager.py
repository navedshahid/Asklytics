from __future__ import annotations

import hashlib
from typing import Optional

from . import feedback_dao as dao
from . import faiss_updater

try:
    import audit_logger  # type: ignore
except Exception:
    audit_logger = None  # type: ignore


def _hash_sql(sql: Optional[str]) -> str:
    import hashlib as _hl
    return _hl.sha1((sql or "").encode("utf-8")).hexdigest()


def record_feedback(xp_id: int, user_id: str, verdict: str, comment: Optional[str], confidence: Optional[float], *, sql_text: Optional[str] = None) -> int:
    sql_hash = _hash_sql(sql_text)
    fb_id = dao.save_feedback(xp_id=xp_id, user_id=user_id or "anon", verdict=verdict, comment=comment, sql_hash=sql_hash, confidence=confidence, masked=True)
    # Update FAISS with positive, confident examples
    try:
        if verdict == 'correct' and (confidence or 0.0) >= 0.7:
            faiss_updater.add_example(int(xp_id), feedback_id=int(fb_id))
    except Exception:
        pass
    # Audit
    try:
        if audit_logger is not None and hasattr(audit_logger, 'log_event'):
            audit_logger.log_event(
                root=None,  # audit_logger uses default path resolver when None
                user_id=user_id or "anon",
                action='feedback_submit',
                resource=str(xp_id),
                masked=True,
                meta={'verdict': verdict, 'confidence': float(confidence or 0.0)}
            )
    except Exception:
        pass
    return int(fb_id)

