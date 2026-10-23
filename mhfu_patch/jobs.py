"""Registry job latar belakang + antrean event untuk SSE."""
import threading
import time
import uuid

MAX_JOBS = 20


class Job:
    def __init__(self, job_id):
        self.id = job_id
        self.state = 'running'          # running | done | error | cancelled
        self.phase = 'starting'
        self.pct = 0
        self.detail = ''
        self.result = None
        self.error = None
        self.cancel = False
        self.events = []
        self.cond = threading.Condition()
        self.started = time.time()

    def emit(self, event):
        with self.cond:
            self.events.append(event)
            if 'phase' in event:
                self.phase = event['phase']
            if 'pct' in event:
                self.pct = event['pct']
            if 'detail' in event:
                self.detail = event['detail']
            self.cond.notify_all()

    def snapshot(self):
        with self.cond:
            return {
                'id': self.id,
                'state': self.state,
                'phase': self.phase,
                'pct': self.pct,
                'detail': self.detail,
                'error': self.error,
                'result': self.result,
                'elapsed': round(time.time() - self.started, 1),
            }


class JobManager:
    def __init__(self):
        self.jobs = {}
        self.active = None
        self.last_output = None
        self.lock = threading.Lock()

    def start(self, fn):
        self.cancel_active()
        job = Job(uuid.uuid4().hex[:12])

        def runner():
            try:
                result = fn(job)
                with job.cond:
                    job.result = result
                    job.state = 'done'
                    job.pct = 100
                    job.cond.notify_all()
                if isinstance(result, dict) and result.get('out'):
                    self.last_output = result['out']
            except BaseException as exc:            # noqa: BLE001 - lapor ke klien
                with job.cond:
                    job.state = 'cancelled' if job.cancel else 'error'
                    job.error = str(exc) or exc.__class__.__name__
                    job.cond.notify_all()

        thread = threading.Thread(target=runner, daemon=True)
        with self.lock:
            self.jobs[job.id] = job
            self.active = job
            for old in list(self.jobs)[:-MAX_JOBS]:
                self.jobs.pop(old, None)
        thread.start()
        return job

    def cancel_active(self):
        with self.lock:
            job = self.active
            if job and job.state == 'running':
                job.cancel = True
                with job.cond:
                    job.cond.notify_all()

    def get(self, job_id):
        with self.lock:
            return self.jobs.get(job_id)

    def active_job(self):
        with self.lock:
            return self.active
