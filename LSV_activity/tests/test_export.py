import io
import unittest
import zipfile
from openpyxl import load_workbook
from lsv_app.core import process_session
from lsv_app.export import workbook_bytes, all_samples_zip, bars_csv, table_txt
from tests.helpers import demo_session


class ExportTests(unittest.TestCase):
    def test_txt_preserves_columns_values_and_missing_cells(self):
        import csv
        result = process_session(demo_session())
        group = result['groups'][0]
        from lsv_app.core import mean_rows, MEAN_HEADERS
        rows = mean_rows(group)
        data = list(csv.reader(io.StringIO(table_txt(rows, MEAN_HEADERS).decode('utf-8-sig')), delimiter='\t'))
        self.assertEqual(data[0], list(MEAN_HEADERS))
        self.assertEqual(len(data), len(rows) + 1)
        self.assertTrue(all(len(row) == 6 for row in data))
        self.assertAlmostEqual(float(data[1][1]), rows[0][1])
        self.assertEqual(table_txt([[1, None]], ['A', 'B']).decode('utf-8-sig'), 'A\tB\n1\t\n')

    def test_excel_formulas_cached_values_and_six_mean_columns(self):
        result = process_session(demo_session())
        content = workbook_bytes(result['groups'][0], result['params'])
        formulas = load_workbook(io.BytesIO(content), data_only=False)
        values = load_workbook(io.BytesIO(content), data_only=True)
        self.assertEqual(values.sheetnames, ['LSV 1', 'LSV 2', 'Média e DP', 'LSV 3'])
        self.assertEqual(formulas['LSV 1']['C2'].value, '=G2*$O$3')
        self.assertEqual(formulas['LSV 1']['D2'].value, '=B2-C2')
        self.assertEqual(values['LSV 1']['I2'].value, 10)
        self.assertEqual(values['LSV 1']['J2'].value, 5)
        mean = values['Média e DP']
        self.assertEqual(mean.max_column, 6)
        self.assertEqual(mean.max_row, 202)
        self.assertAlmostEqual(mean['B2'].value, 12)
        self.assertAlmostEqual(mean['C2'].value, 8 ** .5)
        self.assertTrue(formulas['Média e DP']['B2'].value.startswith('=AVERAGE('))
        for sheet in values:
            for row in sheet:
                self.assertFalse(any(c.data_type == 'e' for c in row))

    def test_zip_and_bars_selection(self):
        state = demo_session()
        state['barTargets'] = [10, 100]
        result = process_session(state)
        with zipfile.ZipFile(io.BytesIO(all_samples_zip(result))) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(sum(n.endswith('.xlsx') for n in archive.namelist()), 2)
            self.assertIn('sessao.json', archive.namelist())
        rows = bars_csv(result).decode('utf-8-sig').splitlines()
        self.assertEqual(len(rows), 5)
        self.assertNotIn('"50"', '\n'.join(rows))


if __name__ == '__main__':
    unittest.main()
