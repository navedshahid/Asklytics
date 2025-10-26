# orchestrator.py
import threading, time
from datetime import datetime
from metadata_store import SessionLocal, Event

class Orchestrator(threading.Thread):
    """Tiny background worker that watches the metadata events table.

    Why this exists:
    - When assets/columns change (harvest, manual edits), we want to refresh
      the vector representation used by retrieval without blocking the request.
    - This thread polls for "schema.change" events and calls `on_reembed(asset_id)`.

    Notes:
    - Runs as a daemon thread so it won't block process exit.
    - Poll interval is kept small (default 2s) for snappy updates.
    """
    def __init__(self, on_reembed, poll_sec: int = 2):
        super().__init__(daemon=True)
        self.on_reembed = on_reembed
        self.poll_sec = poll_sec
        self._stop = threading.Event()

    def run(self):
        """Main polling loop. Picks one pending event at a time and processes it."""
        while not self._stop.is_set():
            try:
                with SessionLocal() as s:
                    ev = s.query(Event).filter(Event.Status=="Pending").order_by(Event.EventId.asc()).first()
                    if not ev:
                        time.sleep(self.poll_sec); continue
                    try:
                        if ev.Topic == "schema.change":
                            payload = ev.PayloadJson or {}
                            asset_id = int(payload.get("AssetId", 0))
                            if asset_id:
                                self.on_reembed(asset_id)  # your embedding+FAISS hook
                        ev.Status = "Done"; ev.ProcessedAt = datetime.utcnow(); s.commit()
                    except Exception as e:
                        ev.Status = "Error"; ev.ErrorMessage = str(e); ev.ProcessedAt = datetime.utcnow(); s.commit()
            except Exception:
                time.sleep(self.poll_sec)

    def stop(self):
        """Signal the thread to stop at the next poll tick."""
        self._stop.set()
