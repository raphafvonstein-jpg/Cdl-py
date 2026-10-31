import copy
import math
import unittest
from lsv_app import core
from tests.helpers import demo_session


class CoreTests(unittest.TestCase):
    def test_decimal_headers_and_blocks(self):
        p = core.parse_text('Potential;Current\n1,4;0,002\n1,5;0,003')
        self.assertEqual(p['data'][0], [1.4, .002])
        self.assertEqual((p['x'], p['y']), (0, 1))
        text = 'E\tI\n0\t1\n1\t2\n\nE\tI\n2\t3\n3\t4\n4\t5'
        self.assertEqual(core.parse_text(text)['other_rows'], 2)
        self.assertEqual(core.parse_text(text, 0)['data'][0], [0, 1])

    def test_impedance(self):
        record = dict(name='EIS', text='Frequency\tZre\tZ″\n100\t.7\t.01\n80\t.85541\t-.003\n60\t1\t-.1', zx=1, zy=2)
        point = core.impedance(record)
        self.assertEqual(point['rs'], .85541)
        self.assertEqual(point['line'], 3)
        self.assertEqual(core.impedance_sign('-Zim / ohm'), 1)
        self.assertEqual(core.impedance_sign('Z″ / ohm'), -1)
        with self.assertRaises(ValueError):
            core.impedance(dict(name='bad', text='X\tY\n1\t0\n2\t-1', zx=0, zy=1))

    def test_rhe_and_columns(self):
        params = core.parameters(dict(referenceElectrode='Ag/AgCl', ph='7', refPotential='.197', temperature='25', eq='1.23'))
        self.assertAlmostEqual(params['shift'], .6111154478076829)
        c = demo_session()['curves'][0]
        c['rs'] = .8
        r = core.treat(c, params)['rows'][0]
        self.assertEqual(r[0], 1.5)
        self.assertAlmostEqual(r[1], 2.111115447807683)
        self.assertEqual(r[2], .008)
        self.assertAlmostEqual(r[3], r[1] - r[2])
        self.assertEqual(r[6:], [.01, 10, 10, 5])

    def test_rhe_no_double_conversion(self):
        p = core.parameters(dict(referenceElectrode='RHE', ph='', refPotential='', eq='1.23'))
        self.assertEqual(p['shift'], 0)
        with self.assertRaises(ValueError):
            core.parameters(dict(referenceElectrode='Ag/AgCl', ph='', refPotential='.197', temperature='25', eq='1.23'))

    def test_means_and_active_area(self):
        r = core.process_session(demo_session())
        g = r['groups'][0]
        self.assertEqual(len(g['mean']), 201)
        self.assertEqual(g['mean'][0]['n'], 2)
        self.assertAlmostEqual(g['mean'][0]['values'][8], 12)
        self.assertAlmostEqual(g['mean'][0]['sd'][8], math.sqrt(8))
        self.assertEqual(len(core.mean_rows(g)[0]), 6)
        state = demo_session()
        state['curves'][0]['electroArea'] = None
        mean = core.process_session(state)['groups'][0]['mean']
        self.assertIsNone(mean[0]['values'][9])
        self.assertIsNotNone(mean[0]['values'][8])

    def test_corrected_oscillation_not_scan_reversal(self):
        c = demo_session()['curves'][0]
        c.update(text='E\tI\n1\t.001\n2\t.03\n3\t.001', rs=100)
        p = core.parameters(demo_session()['settings'])
        treated = core.treat(c, p)
        mean = core.mean_vectors([treated, treated], 3)
        self.assertEqual(mean[1]['values'][3], -1)
        wrong = copy.deepcopy(treated)
        wrong['rows'][1], wrong['rows'][2] = wrong['rows'][2], wrong['rows'][1]
        with self.assertRaises(ValueError):
            core.mean_vectors([wrong, treated])

    def test_bars_mean_sd_and_single(self):
        g = core.process_session(demo_session())['groups'][0]
        self.assertAlmostEqual(g['bars'][50]['mean'], 480)
        self.assertAlmostEqual(g['bars'][50]['sd'], math.sqrt(200))
        self.assertAlmostEqual(g['bars'][100]['mean'], 680)
        self.assertIsNone(core.bar_stats(g['curves'][:1], 50)['sd'])

    def test_no_partial_mean_or_extrapolation(self):
        state = demo_session()
        state['curves'][1]['text'] = 'E\tI\n1.5\t.01\n1.6\t.02'
        g = core.process_session(state)['groups'][0]
        self.assertIn('error', g['bars'][50])
        self.assertNotIn('error', g['bars'][10])

    def test_multiple_crossings(self):
        rows = core.process_session(demo_session())['groups'][0]['curves'][0]['rows']
        rows[-1][8] = 1
        with self.assertRaises(ValueError):
            core.target_vector(rows, 50)

    def test_session_is_not_mutated_and_roundtrip(self):
        state = demo_session()
        before = copy.deepcopy(state)
        core.process_session(state)
        self.assertEqual(state, before)
        loaded = core.load_session(core.session_bytes(state))
        self.assertEqual(loaded['samples'], before['samples'])

    def test_old_session_indices_and_area(self):
        state = demo_session()
        state['version'] = 3
        state['settings'].update(rheMode='already', offset='0', xAxis='9', yAxis='7')
        for c in state['curves']:
            c['factor'], c['electroArea'] = 2, None
        migrated = core.normalize_session(state)
        self.assertEqual(migrated['settings']['xAxis'], '1')
        self.assertEqual(migrated['settings']['yAxis'], '8')
        self.assertEqual(migrated['curves'][0]['electroArea'], 2)

    def test_invalid_session_and_geometry(self):
        state = demo_session()
        state['samples'][1]['name'] = state['samples'][0]['name']
        with self.assertRaises(ValueError):
            core.normalize_session(state)
        state = demo_session()
        state['curves'][0]['area'] = 0
        self.assertFalse(core.process_session(state)['groups'][0]['complete'])


if __name__ == '__main__':
    unittest.main()
