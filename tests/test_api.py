import hashlib
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from tests.common import ORIG_BIN, RESULT_SHA, have, make_synthetic_ipa
from mhfu_patch import server


@unittest.skipUnless(have(ORIG_BIN), 'biner golden tidak tersedia')
class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ipa = make_synthetic_ipa(os.path.join(cls.tmp.name, 'in.ipa'),
                                     open(ORIG_BIN, 'rb').read())
        cls.httpd, cls.state = server.make_server(port=0)
        cls.port = cls.httpd.server_address[1]
        cls.base = 'http://127.0.0.1:%d' % cls.port
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    # ---------- helper ----------
    def req(self, path, body=None, token=True, method=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data,
                                     method=method or ('GET' if body is None else 'POST'))
        if body is not None:
            req.add_header('Content-Type', 'application/json')
        if token:
            req.add_header('X-Patch-Token', self.state['token'])
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            ctype = resp.headers.get('Content-Type', '')
            if 'json' in ctype:
                return resp.status, json.loads(raw.decode())
            return resp.status, raw

    def wait_job(self, job_id, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            _status, data = self.req('/api/job/' + job_id)
            job = data['job']
            if job['state'] != 'running':
                return job
            time.sleep(0.05)
        self.fail('job tidak selesai dalam %.0f s' % timeout)

    def start(self, **over):
        body = {'ipa': self.ipa,
                'out': os.path.join(self.tmp.name, 'out.ipa'),
                'version': '1.00.194'}
        body.update(over)
        _status, data = self.req('/api/start', body)
        return data['job']

    # ---------- tes ----------
    def test_index_injects_token(self):
        status, body = self.req('/', token=False)
        self.assertEqual(status, 200)
        self.assertNotIn(b'__TOKEN__', body)
        self.assertIn(self.state['token'].encode(), body)

    def test_static_css(self):
        status, body = self.req('/style.css', token=False)
        self.assertEqual(status, 200)
        self.assertIn(b'--accent', body)

    def test_auth_required(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req('/api/hello', token=False)
        self.assertEqual(ctx.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req('/api/inspect', {'ipa': self.ipa}, token=False)
        self.assertEqual(ctx.exception.code, 403)

    def test_hello(self):
        _status, data = self.req('/api/hello')
        self.assertTrue(data['ok'])
        self.assertEqual(data['patch_sets'][0]['id'], 'mhfu-ios-1.00.194')

    def test_list(self):
        _status, data = self.req('/api/list', {'path': self.tmp.name})
        self.assertTrue(data['ok'])
        names = [f['name'] for f in data['files']]
        self.assertIn('in.ipa', names)

    def test_inspect(self):
        _status, data = self.req('/api/inspect', {'ipa': self.ipa})
        info = data['info']
        self.assertTrue(info['supported'])
        self.assertEqual(info['steps_pending'], 36)
        self.assertTrue(info['patches_ok'])

    def test_inspect_missing(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req('/api/inspect', {'ipa': '/tidak/ada.ipa'})
        self.assertEqual(ctx.exception.code, 400)

    def test_dry_run_job(self):
        job = self.start(dry_run=True)
        done = self.wait_job(job['id'])
        self.assertEqual(done['state'], 'done', done)
        self.assertTrue(done['result']['dry_run'])
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, 'out.ipa')))

    def test_patch_job_and_sse(self):
        out = os.path.join(self.tmp.name, 'sse.ipa')
        job = self.start(out=out, version='1.00.197')
        url = '%s/api/job/%s/events?token=%s' % (self.base, job['id'],
                                                 self.state['token'])
        events = 0
        final = None
        with urllib.request.urlopen(url, timeout=120) as resp:
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
        self.assertEqual(final['state'], 'done')
        self.assertTrue(os.path.exists(out))
        self.assertEqual(final['result']['version'], '1.00.197')
        self.assertEqual(final['result']['slice_sha256'], RESULT_SHA)
        with open(out, 'rb') as fh:
            self.assertEqual(hashlib.sha256(fh.read()).hexdigest(),
                             final['result']['output_sha256'])

    def test_reveal_only_last_output(self):
        out = os.path.join(self.tmp.name, 'reveal.ipa')
        job = self.start(out=out)
        self.wait_job(job['id'])
        status, data = self.req('/api/reveal', {'path': out})
        self.assertTrue(data['ok'])
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req('/api/reveal', {'path': self.ipa})
        self.assertEqual(ctx.exception.code, 403)

    def test_cancel_unknown(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req('/api/cancel', {'job': 'tidak-ada'})
        self.assertEqual(ctx.exception.code, 404)

    def test_unknown_route(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req('/api/tidak-ada', {})
        self.assertEqual(ctx.exception.code, 404)


if __name__ == '__main__':
    unittest.main()
