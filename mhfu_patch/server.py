"""Local server (127.0.0.1) — FastAPI app, upload API and SSE progress."""
import asyncio
import json
import os
import secrets
import shutil
import threading
import time
import urllib.parse
import webbrowser

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               StreamingResponse)
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import APP_NAME, __version__, engine
from . import manifest as mf
from .jobs import JobManager

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
DEFAULT_WORKDIR = os.environ.get('FUPATCH_WORKSPACE') or os.path.join(
    os.path.expanduser('~'), '.cache', 'fupatch')
MAX_UPLOAD = 4 << 30                 # 4 GB
UPLOAD_TTL = 12 * 3600               # sisa upload yang telantar
MIME = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.ico': 'image/x-icon',
    '.woff2': 'font/woff2',
    '.json': 'application/json; charset=utf-8',
}


def _sweep(root, keep=2):
    """Buang job lama dan upload yang telantar supaya disk tidak penuh."""
    try:
        names = os.listdir(root)
    except OSError:
        return
    jobs = []
    for name in names:
        path = os.path.join(root, name)
        if name.startswith('job-') and os.path.isdir(path):
            jobs.append(path)
        elif name.startswith('upload-') and name.endswith('.ipa'):
            try:
                if time.time() - os.path.getmtime(path) > UPLOAD_TTL:
                    os.remove(path)
            except OSError:
                pass
    jobs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for old in jobs[keep:]:
        shutil.rmtree(old, ignore_errors=True)


def make_app(patch_dir=None, workdir=None):
    app = FastAPI(title=APP_NAME, version=__version__,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.token = secrets.token_urlsafe(18)
    app.state.jobs = JobManager()
    app.state.patch_dir = patch_dir
    app.state.workdir = os.path.abspath(
        os.path.expanduser(workdir or DEFAULT_WORKDIR))
    app.state.uploads = {}
    os.makedirs(app.state.workdir, exist_ok=True)

    # ---------- util ----------
    def fail(code, message):
        raise StarletteHTTPException(code, message)

    def require_token(request: Request, token=None):
        given = request.headers.get('x-patch-token') or token
        if not given or not secrets.compare_digest(given, app.state.token):
            fail(403, 'invalid token')

    @app.middleware('http')
    async def host_guard(request: Request, call_next):
        host = (request.headers.get('host') or '').split(':')[0].strip('[]')
        if host and host not in ('127.0.0.1', 'localhost', '::1'):
            return JSONResponse({'ok': False, 'error': 'host not allowed'},
                                status_code=403)
        return await call_next(request)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request, exc):
        return JSONResponse({'ok': False, 'error': str(exc.detail)},
                            status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def internal_error(_request, exc):
        return JSONResponse(
            {'ok': False, 'error': '%s: %s' % (exc.__class__.__name__, exc)},
            status_code=500)

    # ---------- pages ----------
    @app.get('/favicon.ico')
    async def favicon():
        return JSONResponse({'ok': True}, status_code=204)

    @app.get('/')
    async def index():
        path = os.path.join(WEB_DIR, 'index.html')
        if not os.path.isfile(path):
            fail(500, 'UI build not found — run the build in ui/ first')
        with open(path, encoding='utf-8') as fh:
            html = fh.read().replace('__TOKEN__', app.state.token)
        return HTMLResponse(html, headers={'Cache-Control': 'no-store'})

    @app.get('/assets/{name:path}')
    async def asset(name: str):
        root = os.path.abspath(os.path.join(WEB_DIR, 'assets'))
        path = os.path.abspath(os.path.join(root, name))
        if not path.startswith(root + os.sep) or not os.path.isfile(path):
            fail(404, 'asset not found')
        ext = os.path.splitext(path)[1].lower()
        return FileResponse(
            path, media_type=MIME.get(ext, 'application/octet-stream'),
            headers={'Cache-Control': 'public, max-age=31536000, immutable'})

    # ---------- API ----------
    @app.get('/api/hello')
    async def hello(request: Request, token: str = ''):
        require_token(request, token)
        idx = mf.load_index(app.state.patch_dir)
        return {'ok': True, 'app': APP_NAME, 'version': __version__,
                'default': idx.get('default'),
                'patch_sets': idx.get('sets', []),
                'workdir': app.state.workdir}

    @app.post('/api/inspect')
    async def api_inspect(request: Request):
        require_token(request)
        body = await request.json()
        ipa = body.get('ipa')
        if not ipa:
            fail(400, 'ipa is required')
        try:
            info = await asyncio.to_thread(
                engine.look, os.path.expanduser(ipa), body.get('patch_set'),
                app.state.patch_dir)
        except engine.PatchError as exc:
            fail(400, str(exc))
        version = engine.suggest_version(info)
        info['suggest'] = {'version': version,
                           'out': engine.suggest_output(info['ipa'], version)}
        info['patches_ok'] = info['supported'] and not info['cryptid']
        return {'ok': True, 'info': info}

    @app.post('/api/upload')
    async def api_upload(request: Request):
        require_token(request)
        length = int(request.headers.get('content-length') or 0)
        if length <= 0:
            fail(400, 'empty upload')
        if length > MAX_UPLOAD:
            fail(413, 'file too large (max 4 GB)')
        name = urllib.parse.unquote(
            request.headers.get('x-filename') or 'input.ipa')
        root = app.state.workdir
        _sweep(root)
        token = secrets.token_hex(8)
        dest = os.path.join(root, 'upload-%s.ipa' % token)
        received = 0
        try:
            with open(dest, 'wb') as fh:
                async for chunk in request.stream():
                    if not chunk:
                        continue
                    received += len(chunk)
                    if received > MAX_UPLOAD:
                        raise StarletteHTTPException(413, 'file too large')
                    await asyncio.to_thread(fh.write, chunk)
        except BaseException:
            try:
                os.remove(dest)
            except OSError:
                pass
            raise
        if received != length:
            os.remove(dest)
            fail(400, 'upload incomplete')
        try:
            info = await asyncio.to_thread(
                engine.look, dest, None, app.state.patch_dir)
        except Exception as exc:            # noqa: BLE001 - input pengguna
            os.remove(dest)
            fail(400, 'not a readable IPA: %s' % exc)
        if not info['supported']:
            os.remove(dest)
            fail(400, info['reason'] or 'unsupported IPA')
        version = engine.suggest_version(info)
        job_dir = os.path.join(root, 'job-' + token)
        os.makedirs(job_dir, exist_ok=True)
        app.state.uploads[token] = {
            'path': dest,
            'name': name,
            'out': os.path.join(job_dir, 'MHFU_patched_%s.ipa' % version),
            'version': version,
            'dir': job_dir,
        }
        return {'ok': True, 'upload': token, 'name': name, 'size': received,
                'version': version, 'app': info.get('app_name')}

    @app.post('/api/start')
    async def api_start(request: Request):
        require_token(request)
        body = await request.json()
        upload = body.get('upload')
        entry = app.state.uploads.get(upload) if upload else None
        if not entry:
            fail(404, 'upload expired, choose the file again')

        def run(job):
            try:
                report = engine.patch(
                    entry['path'], entry['out'], version=entry['version'],
                    on_event=job.emit, is_cancelled=lambda: job.cancel,
                    directory=app.state.patch_dir, force=True)
                report['out_name'] = os.path.basename(report.get('out') or '')
                return report
            finally:
                app.state.uploads.pop(upload, None)
                try:
                    os.remove(entry['path'])
                except OSError:
                    pass

        job = app.state.jobs.start(run)
        return {'ok': True, 'job': job.snapshot()}

    @app.post('/api/cancel')
    async def api_cancel(request: Request):
        require_token(request)
        body = await request.json()
        job_id = body.get('job')
        job = app.state.jobs.get(job_id) if job_id else None
        if not job:
            job = app.state.jobs.active_job()
        if not job:
            fail(404, 'job not found')
        job.cancel = True
        with job.cond:
            job.cond.notify_all()
        return {'ok': True}

    @app.get('/api/job/{job_id}')
    async def api_job(job_id: str, request: Request):
        require_token(request)
        job = app.state.jobs.get(job_id)
        if not job:
            fail(404, 'job not found')
        return {'ok': True, 'job': job.snapshot()}

    @app.get('/api/job/{job_id}/events')
    async def api_job_events(job_id: str, request: Request, token: str = ''):
        require_token(request, token)
        job = app.state.jobs.get(job_id)
        if not job:
            fail(404, 'job not found')

        async def stream():
            sent = 0
            while True:
                events = job.events[sent:]
                sent += len(events)
                for event in events:
                    yield 'data: %s\n\n' % json.dumps(event)
                if job.state != 'running':
                    snap = job.snapshot()
                    yield 'data: %s\n\n' % json.dumps(
                        {'done': True, 'job': snap})
                    return
                if not events:
                    yield ': ping\n\n'
                await asyncio.sleep(0.1)

        return StreamingResponse(
            stream(), media_type='text/event-stream',
            headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})

    @app.get('/api/download/{job_id}')
    async def api_download(job_id: str, request: Request, token: str = ''):
        require_token(request, token)
        job = app.state.jobs.get(job_id)
        if not job:
            fail(404, 'job not found')
        snap = job.snapshot()
        out = (snap.get('result') or {}).get('out') if snap['state'] == 'done' else None
        if not out:
            fail(404, 'result is not ready')
        path = os.path.abspath(out)
        root = os.path.abspath(app.state.workdir)
        if not path.startswith(root + os.sep) or not os.path.isfile(path):
            fail(404, 'result file not found')
        return FileResponse(path, media_type='application/octet-stream',
                            filename=os.path.basename(path),
                            headers={'Cache-Control': 'no-store'})

    @app.api_route('/api/{rest:path}',
                   methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
    async def api_not_found(rest: str):
        fail(404, 'not found')

    # ---------- static (SPA) ----------
    @app.get('/{path:path}')
    async def static_file(path: str):
        if path.startswith('api/'):
            fail(404, 'not found')
        root = os.path.abspath(WEB_DIR)
        target = os.path.abspath(os.path.join(root, urllib.parse.unquote(path)))
        if not target.startswith(root + os.sep) or not os.path.isfile(target):
            fail(404, 'not found')
        ext = os.path.splitext(target)[1].lower()
        return FileResponse(target, media_type=MIME.get(
            ext, 'application/octet-stream'))

    return app


class ServerHandle:
    """Small wrapper so tests can start/stop the server easily."""

    def __init__(self, server, app, thread):
        self.server = server
        self.app = app
        self.thread = thread
        self.server_address = server.servers[0].sockets[0].getsockname()
        self.state = {
            'token': app.state.token,
            'jobs': app.state.jobs,
            'patch_dir': app.state.patch_dir,
            'workdir': app.state.workdir,
            'uploads': app.state.uploads,
            'app': app,
        }

    def shutdown(self):
        self.server.should_exit = True
        self.thread.join(timeout=10)

    def server_close(self):
        pass


def make_server(host='127.0.0.1', port=0, patch_dir=None, workdir=None):
    app = make_app(patch_dir=patch_dir, workdir=workdir)
    config = uvicorn.Config(app, host=host, port=port, log_level='warning')
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError('server did not start')
        time.sleep(0.02)
    return ServerHandle(server, app, thread), app.state


def serve(host='127.0.0.1', port=8765, open_browser=False, patch_dir=None,
          workdir=None):
    app = make_app(patch_dir=patch_dir, workdir=workdir)
    shown = '127.0.0.1' if host in ('0.0.0.0', '') else host
    url = 'http://%s:%d/' % (shown, port)
    print('%s %s' % (APP_NAME, __version__))
    print('open in browser: %s' % url)
    print('workspace: %s' % app.state.workdir)
    print('press Ctrl+C to stop')
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=port, log_level='warning')
