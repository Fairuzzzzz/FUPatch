"""Server lokal (127.0.0.1) + API JSON + SSE untuk UI web."""
import json
import os
import secrets
import shutil
import subprocess
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import APP_NAME, __version__, engine
from . import manifest as mf
from .jobs import JobManager

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
MAX_BODY = 1 << 20
MIME = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
        '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml'}


class Handler(BaseHTTPRequestHandler):
    state = None                     # diisi oleh serve()
    server_version = 'MHFUPatcher/' + __version__

    # ---------- util ----------
    def log_message(self, fmt, *args):      # tenang: jangan banjiri terminal
        pass

    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _error(self, message, code=400):
        self._json({'ok': False, 'error': message}, code)

    def _body(self):
        length = int(self.headers.get('Content-Length') or 0)
        if length > MAX_BODY:
            raise ValueError('body terlalu besar')
        raw = self.rfile.read(length) if length else b'{}'
        return json.loads(raw.decode('utf-8') or '{}')

    def _token_ok(self, query=None):
        token = self.state['token']
        given = self.headers.get('X-Patch-Token')
        if not given and query:
            given = query
        return secrets.compare_digest(given or '', token)

    def _host_ok(self):
        host = (self.headers.get('Host') or '').split(':')[0]
        return host in ('127.0.0.1', 'localhost', '')

    # ---------- GET ----------
    def do_GET(self):                      # noqa: N802
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            if path == '/':
                return self._static('index.html')
            if path in ('/app.js', '/style.css'):
                return self._static(path[1:])
            if path == '/favicon.ico':
                return self._send(204, b'', 'image/x-icon')
            if not self._host_ok():
                return self._error('host tidak diizinkan', 403)
            if path == '/api/hello':
                if not self._token_ok(parsed.query and urllib.parse.parse_qs(parsed.query).get('token', [None])[0]):
                    return self._error('token tidak valid', 403)
                idx = mf.load_index(self.state['patch_dir'])
                return self._json({
                    'ok': True, 'app': APP_NAME, 'version': __version__,
                    'default': idx.get('default'),
                    'patch_sets': idx.get('sets', []),
                    'home': os.path.expanduser('~'),
                })
            if path.startswith('/api/job/'):
                return self._job_get(path, parsed)
            return self._error('tidak ditemukan', 404)
        except Exception as exc:           # noqa: BLE001
            return self._error('%s: %s' % (exc.__class__.__name__, exc), 500)

    def _static(self, name):
        path = os.path.join(WEB_DIR, name)
        if not os.path.isfile(path):
            return self._error('aset tidak ada', 404)
        ext = os.path.splitext(name)[1]
        with open(path, 'rb') as fh:
            body = fh.read()
        if name == 'index.html':
            body = (body.replace(b'__TOKEN__', self.state['token'].encode())
                        .replace(b'__VERSION__', __version__.encode()))
        self._send(200, body, MIME.get(ext, 'application/octet-stream'))

    def _job_get(self, path, parsed):
        parts = path.strip('/').split('/')     # api/job/<id>[/events]
        if len(parts) < 3:
            return self._error('job tidak valid', 404)
        job = self.state['jobs'].get(parts[2])
        if not job:
            return self._error('job tidak ditemukan', 404)
        if len(parts) == 3:
            if not self._token_ok(self.headers.get('X-Patch-Token')):
                return self._error('token tidak valid', 403)
            return self._json({'ok': True, 'job': job.snapshot()})
        if parts[3] != 'events':
            return self._error('tidak ditemukan', 404)
        token = urllib.parse.parse_qs(parsed.query).get('token', [None])[0]
        if not self._token_ok(token):
            return self._error('token tidak valid', 403)
        return self._stream(job)

    def _stream(self, job):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'close')
        self.end_headers()
        sent = 0
        try:
            while True:
                with job.cond:
                    if len(job.events) <= sent and job.state == 'running':
                        job.cond.wait(timeout=5)
                    events = job.events[sent:]
                    sent += len(events)
                    state = job.state
                    snap = job.snapshot()
                for event in events:
                    self.wfile.write(('data: %s\n\n' % json.dumps(event)).encode())
                if state != 'running':
                    self.wfile.write(('data: %s\n\n' % json.dumps(
                        {'done': True, 'job': snap})).encode())
                    self.wfile.flush()
                    return
                self.wfile.write(b': ping\n\n')
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    # ---------- POST ----------
    def do_POST(self):                     # noqa: N802
        try:
            if not self._host_ok():
                return self._error('host tidak diizinkan', 403)
            if not self._token_ok(self.headers.get('X-Patch-Token')):
                return self._error('token tidak valid', 403)
            path = urllib.parse.urlparse(self.path).path
            body = self._body()
            if path == '/api/list':
                return self._api_list(body)
            if path == '/api/inspect':
                return self._api_inspect(body)
            if path == '/api/start':
                return self._api_start(body)
            if path == '/api/cancel':
                return self._api_cancel(body)
            if path == '/api/reveal':
                return self._api_reveal(body)
            return self._error('tidak ditemukan', 404)
        except engine.PatchError as exc:
            return self._error(str(exc), 400)
        except Exception as exc:           # noqa: BLE001
            return self._error('%s: %s' % (exc.__class__.__name__, exc), 500)

    def _api_list(self, body):
        path = os.path.abspath(os.path.expanduser(body.get('path') or '~'))
        if not os.path.isdir(path):
            return self._error('folder tidak ada: %s' % path)
        dirs, files = [], []
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if entry.name.startswith('.'):
                        continue
                    try:
                        if entry.is_dir():
                            dirs.append(entry.name)
                        elif entry.name.lower().endswith('.ipa'):
                            st = entry.stat()
                            files.append({'name': entry.name, 'size': st.st_size})
                    except OSError:
                        continue
        except PermissionError:
            return self._error('tidak boleh membaca folder ini', 403)
        dirs.sort(key=str.lower)
        files.sort(key=lambda f: f['name'].lower())
        return self._json({'ok': True, 'path': path,
                           'parent': os.path.dirname(path) if path != '/' else None,
                           'dirs': dirs, 'files': files})

    def _api_inspect(self, body):
        ipa = body.get('ipa')
        if not ipa:
            return self._error('ipa wajib diisi')
        info = engine.look(os.path.expanduser(ipa),
                           patch_set=body.get('patch_set'),
                           directory=self.state['patch_dir'])
        folder = os.path.dirname(os.path.abspath(os.path.expanduser(ipa)))
        try:
            free = shutil.disk_usage(folder).free
        except OSError:
            free = None
        info['free_space'] = free
        info['patches_ok'] = info['supported'] and not info['cryptid']
        return self._json({'ok': True, 'info': info})

    def _api_start(self, body):
        ipa = os.path.expanduser(body.get('ipa') or '')
        out = os.path.expanduser(body.get('out') or '')
        if not ipa or not out:
            return self._error('ipa dan out wajib diisi')
        version = body.get('version') or None
        keep_fat = bool(body.get('keep_fat'))
        dry_run = bool(body.get('dry_run'))
        force = bool(body.get('force'))
        patch_set = body.get('patch_set') or None
        directory = self.state['patch_dir']

        def run(job):
            return engine.patch(ipa, out, version=version, keep_fat=keep_fat,
                                dry_run=dry_run, on_event=job.emit,
                                is_cancelled=lambda: job.cancel,
                                directory=directory, patch_set=patch_set,
                                force=force)

        job = self.state['jobs'].start(run)
        return self._json({'ok': True, 'job': job.snapshot()})

    def _api_cancel(self, body):
        job_id = body.get('job')
        job = self.state['jobs'].get(job_id) if job_id else self.state['jobs'].active_job()
        if not job:
            return self._error('job tidak ditemukan', 404)
        job.cancel = True
        with job.cond:
            job.cond.notify_all()
        return self._json({'ok': True})

    def _api_reveal(self, body):
        path = body.get('path')
        last = self.state['jobs'].last_output
        if not path or not last:
            return self._error('belum ada hasil')
        path = os.path.abspath(os.path.expanduser(path))
        if os.path.abspath(last) != path:
            return self._error('hanya folder hasil terakhir yang boleh dibuka', 403)
        subprocess.Popen(['xdg-open', os.path.dirname(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return self._json({'ok': True})


def make_server(host='127.0.0.1', port=0, patch_dir=None):
    Handler.state = {'token': secrets.token_urlsafe(18),
                     'jobs': JobManager(),
                     'patch_dir': patch_dir}
    httpd = ThreadingHTTPServer((host, port), Handler)
    return httpd, Handler.state


def serve(host='127.0.0.1', port=8765, open_browser=False, patch_dir=None):
    httpd, _state = make_server(host, port, patch_dir)
    shown = '127.0.0.1' if host in ('0.0.0.0', '') else host
    url = 'http://%s:%d/' % (shown, port)
    print('%s %s' % (APP_NAME, __version__))
    print('buka di browser: %s' % url)
    print('tekan Ctrl+C untuk berhenti')
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nberhenti.')
    finally:
        httpd.server_close()
