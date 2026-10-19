#!/usr/bin/env python3
import importlib.util, tempfile, pathlib, unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('preflight_cache', ROOT/'.aidp/scripts/preflight_cache.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class PreflightCacheTest(unittest.TestCase):
    def test_success_same_run_and_fingerprint_hits(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)/'plan.md'; p.write_text('a', encoding='utf-8')
            fp = m.fingerprint(d, ['plan.md'], ['origin=https://example.com'])
            self.assertTrue(m.put(d, 'tick-1', 'login-smoke', fp, 'ok', 'probe passed'))
            hit = m.get(d, 'tick-1', 'login-smoke', fp)
            self.assertEqual(hit['detail'], 'probe passed')
            self.assertIsNone(m.get(d, 'tick-2', 'login-smoke', fp))
            p.write_text('changed', encoding='utf-8')
            self.assertIsNone(m.get(d, 'tick-1', 'login-smoke', m.fingerprint(d, ['plan.md'], ['origin=https://example.com'])))

    def test_failures_are_not_cached(self):
        with tempfile.TemporaryDirectory() as d:
            fp = m.fingerprint(d)
            self.assertFalse(m.put(d, 'tick-1', 'chrome', fp, 'blocked', 'down'))
            self.assertIsNone(m.get(d, 'tick-1', 'chrome', fp))

if __name__ == '__main__': unittest.main(verbosity=2)
