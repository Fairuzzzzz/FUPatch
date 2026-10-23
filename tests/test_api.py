import hashlib
import json
import os
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

from tests.common import ORIG_BIN, RESULT_SHA, have, make_synthetic_ipa
from mhfu_patch import server


@unittest.skipUnless(have(ORIG_BIN), 'golden binary not available')
class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.work = os.path.join(cls.tmp.name, 'work')
        with open(ORIG_BIN, 'rb') as fh:
            exe = fh.read()
        cls.ipa = make_synthetic_ipa(os.path.join(cls.tmp.name, 'in.ipa'), exe)
        cls.httpd, cls.state = server.make_server(port=0, workdir=cls.work)
        cls.port = cls.httpd.server_address[1]
        cls.base = 'http://127.0.0.1:%d' % cls.port

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    # ---------- helpers ----------
    def req(self, path, body=None, token=True, method=None, raw=None,
            headers=None):
        data = raw if raw is not None else (
            None if body is None else json.dumps(body).encode())
        req = urllib.request.Request(
            self.base + path, data=data,
            method=method or ('GET' if data is None else 'POST'))
        if body is not None:
            req.add_header('Content-Type', 'application/json')
        if token:
            req.add_header('X-Patch-Token', self.state['token'])
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = resp.read()
                ctype = resp.headers.get('Content-Type', '')
                if 'json' in ctype:
                    return resp.status, json.loads(payload.decode())
                return resp.status, payload
        except urllib.error.HTTPError as exc:
            exc.read()
            exc.close()
            raise

    def upload(self, path=None, name=None, token=True):
        path = path or self.ipa
        with open(path, 'rb') as fh:
            blob = fh.read()
        headers = {
            'Content-Type': 'application/octet-stream',
            'X-Filename': urllib.parse.quote(name or os.path.basename(path)),
        }
        _status, data = self.req('/api/upload', raw=blob, token=token,
                                 headers=headers)
        return data

    def start(self, upload_id):
        _status, data = self.req('/api/start', {'upload': upload_id})
        return data['job']

    def wait_job(self, job_id, timeout=120):
        deadline = time.time() + timeout
        while time.time() < deadline:
            _status, data = self.req('/api/job/' + job_id)
            job = data['job']
            if job['state'] != 'running':
                return job
            time.sleep(0.05)
        self.fail('job did not finish in %.0f s' % timeout)

    def patch_once(self):
        up = self.upload(name='run.ipa')
        job = self.start(up['upload'])
        done = self.wait_job(job['id'])
        self.assertEqual(done['state'], 'done', done)
        return done

    # ---------- static ----------
    def test_index_injects_token(self):
        status, body = self.req('/', token=False)
        self.assertEqual(status, 200)
        self.assertNotIn(b'__TOKEN__', body)
        self.assertIn(self.state['token'].encode(), body)

    def test_static_css(self):
        import re
        _status, html = self.req('/', token=False)
        match = re.search(rb'/assets/[^\"\']+\.css', html)
        self.assertIsNotNone(match, 'index.html does not reference built CSS')
        status, body = self.req(match.group(0).decode(), token=False)
        self.assertEqual(status, 200)
        self.assertIn(b'--background', body)

    # ---------- auth ----------
    def test_auth_required(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req('/api/hello', token=False)
        self.assertEqual(ctx.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req('/api/inspect', {'ipa': self.ipa}, token=False)
        self.assertEqual(ctx.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req('/api/upload', raw=b'x', token=False,
                     headers={'X-Filename': 'x.ipa'})
        self.assertEqual(ctx.exception.code, 403)

    def test_hello(self):
        _status, data = self.req('/api/hello')
        self.assertTrue(data['ok'])
        self.assertEqual(data['patch_sets'][0]['id'], 'mhfu-ios')

    # ---------- inspect ----------
    def test_inspect(self):
        _status, data = self.req('/api/inspect', {'ipa': self.ipa})
        info = data['info']
        self.assertTrue(info['supported'])
        self.assertEqual(info['steps_pending'], 36)
        self.assertTrue(info['patches_ok'])

    def test_inspect_missing(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req('/api/inspect', {'ipa': '/does/not/exist.ipa'})
        self.assertEqual(ctx.exception.code, 400)

    def test_suggest(self):
        _status, data = self.req('/api/inspect', {'ipa': self.ipa})
        suggest = data['info']['suggest']
        self.assertTrue(suggest['out'].endswith('MHFU_patched.ipa'))
        self.assertNotEqual(suggest['out'], self.ipa)

    # ---------- upload ----------
    def test_upload_accepts_any_name(self):
        data = self.upload(name='notes.txt')
        self.assertTrue(data['ok'])
        self.assertTrue(data['upload'])

    def test_upload_rejects_garbage(self):
        junk = os.path.join(self.tmp.name, 'junk.ipa')
        with open(junk, 'wb') as fh:
            fh.write(b'not a zip at all' * 100)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.upload(junk)
        self.assertEqual(ctx.exception.code, 400)

    def test_upload_reports_size(self):
        data = self.upload(name='size.ipa')
        self.assertTrue(data['ok'])
        self.assertEqual(data['size'], os.path.getsize(self.ipa))
        self.assertTrue(data['upload'])

    # ---------- jobs ----------
    def test_patch_job_and_sse(self):
        up = self.upload(name='sse.ipa')
        job = self.start(up['upload'])
        url = '%s/api/job/%s/events?token=%s' % (
            self.base, job['id'], self.state['token'])
        events = 0
        final = None
        with urllib.request.urlopen(url, timeout=180) as resp:
            for raw in resp:
                line = raw.decode().strip()
                if not line.startswith('data: '):
                    continue
                payload = json.loads(line[6:])
                if payload.get('done'):
                    final = payload['job']
                    break
                events += 1
        self.assertGreater(events, 0)
        self.assertIsNotNone(final)
        self.assertEqual(final['state'], 'done', final)
        self.assertEqual(final['result']['version'], '1.00.11')
        self.assertEqual(final['result']['slice_sha256'], RESULT_SHA)
        self.assertEqual(final['result']['out_name'], 'MHFU_patched.ipa')
        out = final['result']['out']
        self.assertTrue(os.path.isabs(out))
        with open(out, 'rb') as fh:
            self.assertEqual(hashlib.sha256(fh.read()).hexdigest(),
                             final['result']['output_sha256'])
        # upload temp file is removed once the job is done
        self.assertEqual(self.state['uploads'], {})

    def test_download(self):
        done = self.patch_once()
        path = '/api/download/%s?token=%s' % (
            done['id'], urllib.parse.quote(self.state['token']))
        status, blob = self.req(path, token=False)
        self.assertEqual(status, 200)
        self.assertEqual(hashlib.sha256(blob).hexdigest(),
                         done['result']['output_sha256'])

    def test_download_unknown_job(self):
        path = '/api/download/nope?token=%s' % urllib.parse.quote(
            self.state['token'])
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req(path, token=False)
        self.assertEqual(ctx.exception.code, 404)

    def test_download_requires_token(self):
        done = self.patch_once()
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req('/api/download/' + done['id'], token=False)
        self.assertEqual(ctx.exception.code, 403)

    def test_cancel_unknown(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req('/api/cancel', {'job': 'does-not-exist'})
        self.assertEqual(ctx.exception.code, 404)

    def test_unknown_route(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req('/api/does-not-exist', {})
        self.assertEqual(ctx.exception.code, 404)


if __name__ == '__main__':
    unittest.main()
