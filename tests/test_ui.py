from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest
from tests.helpers import demo_session

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


class UITests(unittest.TestCase):
    def app(self, demo=True):
        at = AppTest.from_file(APP, default_timeout=60)
        if demo:
            at.session_state['lsv_state'] = demo_session()
        at.run()
        self.assertEqual(len(at.exception), 0)
        return at

    def test_first_open_and_name_persistence(self):
        at = self.app(False)
        at.text_input(key='e0_sample_1_name').input('Minha amostra').run()
        self.assertEqual(at.session_state['lsv_state']['samples'][0]['name'], 'Minha amostra')
        at.radio(key='view').set_value('Tratamento').run()
        at.radio(key='view').set_value('Amostras').run()
        self.assertEqual(at.text_input(key='e0_sample_1_name').value, 'Minha amostra')
        self.assertEqual(len(at.exception), 0)

    def test_duplicate_draft_not_overwritten(self):
        at = self.app()
        at.text_input(key='e0_sample_1_name').input('Amostra B').run()
        self.assertEqual(at.text_input(key='e0_sample_1_name').value, 'Amostra B')
        self.assertEqual(at.session_state['lsv_state']['samples'][0]['name'], 'Amostra A')
        self.assertGreater(len(at.error), 0)

    def test_workbooks_and_curves_and_bars(self):
        at = self.app()
        at.radio(key='view').set_value('Planilhas').run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.tabs), 4)
        self.assertEqual(sum(len(df.value.columns) == 6 for df in at.dataframe), 1)
        at.radio(key='view').set_value('Gráficos').run()
        self.assertEqual(len(at.exception), 0)
        at.selectbox(key='e0_setting_chartKind').set_value('bars').run()
        self.assertEqual(len(at.exception), 0)
        at.multiselect(key='e0_targets').set_value([10, 100]).run()
        self.assertEqual(at.session_state['lsv_state']['barTargets'], [10, 100])
        at.multiselect(key='e0_targets').set_value([]).run()
        self.assertEqual(len(at.exception), 0)

    def test_sessions_are_isolated(self):
        first, second = self.app(False), self.app(False)
        first.text_input(key='e0_sample_1_name').input('Só minha').run()
        self.assertEqual(second.session_state['lsv_state']['samples'][0]['name'], 'Amostra 1')


if __name__ == '__main__':
    unittest.main()
