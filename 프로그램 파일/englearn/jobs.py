"""Background jobs with progress, messages and cancel."""
import logging
import threading
import time
import traceback
import uuid

log = logging.getLogger("englearn")


class Job:
    def __init__(self, kind, pid, title):
        self.id = uuid.uuid4().hex[:8]
        self.kind = kind
        self.pid = pid
        self.title = title
        self.progress = 0.0
        self.msg = ""
        self.state = "running"   # running | done | error | cancelled
        self.error = ""
        self.started = time.time()
        self.ended = None
        self._cancel = threading.Event()

    def cancelled(self):
        return self._cancel.is_set()

    def set(self, progress=None, msg=None):
        if progress is not None:
            self.progress = max(0.0, min(1.0, float(progress)))
        if msg is not None:
            self.msg = msg

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "pid": self.pid, "title": self.title,
                "progress": round(self.progress, 4), "msg": self.msg, "state": self.state,
                "error": self.error, "started": self.started, "ended": self.ended}


class Jobs:
    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def start(self, kind, pid, title, fn):
        with self._lock:
            for j in self._jobs.values():
                if j.kind == kind and j.pid == pid and j.state == "running":
                    return j
            job = Job(kind, pid, title)
            self._jobs[job.id] = job

        def run():
            try:
                fn(job)
                if job.cancelled():
                    job.state = "cancelled"
                else:
                    job.state = "done"
                    job.progress = 1.0
            except Exception as e:  # noqa: BLE001
                if job.cancelled():
                    job.state = "cancelled"
                else:
                    job.state = "error"
                    job.error = str(e) or type(e).__name__
                    log.warning("%s 실패: %s", title, job.error)
                    log.info("job %s traceback:\n%s", kind, traceback.format_exc())
            finally:
                job.ended = time.time()

        threading.Thread(target=run, daemon=True, name=f"job-{kind}").start()
        return job

    def cancel(self, jid):
        j = self._jobs.get(jid)
        if j:
            j._cancel.set()
        return j

    def running(self, kind=None, pid=None):
        return [j for j in self._jobs.values() if j.state == "running"
                and (kind is None or j.kind == kind) and (pid is None or j.pid == pid)]

    def list(self, keep_secs=900):
        now = time.time()
        with self._lock:
            for jid in [k for k, j in self._jobs.items() if j.ended and now - j.ended > keep_secs]:
                self._jobs.pop(jid, None)
            return [j.to_dict() for j in sorted(self._jobs.values(), key=lambda j: j.started)]


jobs = Jobs()
