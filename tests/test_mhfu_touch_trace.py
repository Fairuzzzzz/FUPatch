import os
import struct
import unittest

from tools import mhfu_touch_trace


class MhfuTouchTraceHelpersTest(unittest.TestCase):
    def test_filespec_path_uses_fullpath_and_fallback(self):
        class FullPathSpec:
            fullpath = '/Mac/Applications/MH Unite'

            def IsValid(self):
                return True

        class LegacySpec:
            fullpath = property(
                lambda self: (_ for _ in ()).throw(AttributeError('no fullpath')))

            def IsValid(self):
                return True

            def GetDirectory(self):
                return '/Mac/Applications'

            def GetFilename(self):
                return 'MH Unite'

        self.assertEqual(
            mhfu_touch_trace._file_spec_fullpath(FullPathSpec()),
            '/Mac/Applications/MH Unite')
        self.assertEqual(
            mhfu_touch_trace._file_spec_fullpath(LegacySpec()),
            os.path.join('/Mac/Applications', 'MH Unite'))

    def test_runtime_address_uses_supplied_slide(self):
        unslid = 0x10046328C
        slide = 0x4BC0000
        self.assertEqual(
            mhfu_touch_trace.runtime_address(unslid, slide),
            unslid + slide)
        self.assertEqual(
            mhfu_touch_trace.calculate_slide(unslid, unslid + slide),
            slide)

    def test_decodes_float_register_representations(self):
        bits = struct.unpack('<Q', struct.pack('<d', 123.5))[0]
        self.assertEqual(
            mhfu_touch_trace._decode_float_register(hex(bits)), 123.5)
        self.assertEqual(
            mhfu_touch_trace._decode_float_register('123.5'), 123.5)
        self.assertIsNone(
            mhfu_touch_trace._decode_float_register('not-a-register'))

    def test_session_comparison_reports_points_and_event_kinds(self):
        hamburger = [
            {'kind': 'touchesBegan', 'stack': [{'function': 'hxViewController'}]},
            {'kind': 'touchLocationBegan', 'point': {'x': 900.0, 'y': 100.0}},
        ]
        outside = [
            {'kind': 'touchesBegan', 'stack': [{'function': 'hxViewController'}]},
            {'kind': 'touchLocationBegan', 'point': {'x': 820.0, 'y': 100.0}},
        ]
        report = mhfu_touch_trace.compare_sessions(hamburger, outside)
        self.assertEqual(report['point_delta'], {
            'mean_x_second_minus_first': -80.0,
            'mean_y_second_minus_first': 0.0,
        })
        self.assertEqual(report['first']['by_kind']['touchesBegan'], 1)
        self.assertIn('do not prove', report['interpretation'])

    def test_status_retains_stopped_event_count(self):
        state = {
            'active': None,
            'last_session': {'label': 'hamburger', 'event_count': 5},
            'sessions': {'hamburger': [None] * 5},
        }
        result = mhfu_touch_trace.status_snapshot(state)
        self.assertEqual(result['state'], 'stopped')
        self.assertEqual(result['label'], 'hamburger')
        self.assertEqual(result['events'], 5)

    def test_native_hit_test_mode_installs_only_native_sites(self):
        label, options = mhfu_touch_trace._parse_start(
            'hamburger-native --native-hit-test --native-interval 0.2 '
            '--max-events 40')
        sites = mhfu_touch_trace._sites_for_options(options)
        self.assertEqual(label, 'hamburger-native')
        self.assertEqual(options['native_interval'], 0.2)
        self.assertEqual(options['max_events'], 40)
        self.assertEqual(
            [site[0] for site in sites],
            ['nativeRectTest', 'nativeRectTestResult'])
        self.assertEqual(
            [site[1] for site in sites],
            [0x100460D44, 0x100460D98])
        self.assertTrue(all(site[3] for site in sites))

    def test_invalid_lldb_module_does_not_break_helper_import(self):
        self.assertIsNone(mhfu_touch_trace.lldb)


if __name__ == '__main__':
    unittest.main()
