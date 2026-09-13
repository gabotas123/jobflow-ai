"""Run with python -m jobflow.scheduler, or JOBFLOW_SCHEDULER=true for one web process."""
import logging
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from .db import SessionLocal
from .career import Preferences
from .google_integration import send_digest, sync_gmail
log=logging.getLogger(__name__)

def tick():
    with SessionLocal() as db:
        ids=[p.profile_id for p in db.query(Preferences)]
    for pid in ids:
        with SessionLocal() as db:
            p=db.get(Preferences,pid);data=dict(p.data);now=datetime.now(ZoneInfo(data.get('timezone','America/Lima')))
            try:
                if data.get('gmail_sync_enabled'):
                    last=data.get('gmail_last_sync')
                    if not last or (now-datetime.fromisoformat(last)).total_seconds()>900:sync_gmail(db,pid)
                if data.get('digest_enabled') and now.strftime('%H:%M')>=data.get('digest_time','21:00'):send_digest(db,pid)
            except Exception:
                db.rollback()
                p=db.get(Preferences,pid);p.data={**p.data,'scheduler_error':'Una tarea requiere revisar la conexión.','scheduler_checked_at':now.isoformat()};db.commit()
                log.warning('Scheduled task requires attention for profile %s',pid)

def loop(stop):
    while not stop.is_set():
        try:tick()
        except Exception:log.warning('Scheduler could not complete this cycle')
        stop.wait(60)

if __name__=='__main__':
    from .seed import ensure_seed
    ensure_seed();loop(threading.Event())
