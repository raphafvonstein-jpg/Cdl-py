import unittest
from unittest.mock import patch
from lsv_app import ui, core


class Upload:
    def __init__(self, name, text):
        self.name = name
        self.data = text.encode()
    def getvalue(self):
        return self.data


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.memory = {'lsv_state': core.new_session(), 'lsv_epoch': 0}
        self.patcher = patch.object(ui.st, 'session_state', self.memory)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def file(self, name='lsv.txt'):
        return Upload(name, 'Potential/V\tCurrent/A\n1.4\t.01\n1.5\t.02\n1.6\t.03')

    def test_bulk_and_replacement_preserve_pair(self):
        self.memory['files'] = [self.file(str(i)+'.txt') for i in range(3)]
        ui.upload_bulk(1, 'files')
        self.assertEqual([c['rep'] for c in ui.state()['curves']], [1, 2, 3])
        self.memory['extra'] = [self.file()]
        ui.upload_bulk(1, 'extra')
        self.assertEqual(len(ui.state()['curves']), 3)
        self.assertIn('posição', self.memory['lsv_error'])
        self.memory['eis'] = Upload('EIS.txt', 'Zre\t-Zim\n.7\t-.01\n.8\t.01\n1\t.1')
        ui.upload_eis(1, 1, 'eis')
        original = ui.find_curve(1, 1)
        original['area'], original['electroArea'] = 2, 8
        eid, cid = original['eisId'], original['id']
        self.memory['single'] = self.file('novo.txt')
        ui.upload_lsv(1, 1, 'single')
        replaced = ui.find_curve(1, 1)
        self.assertEqual((replaced['id'], replaced['eisId'], replaced['area'], replaced['electroArea']), (cid, eid, 2, 8))
        ui.remove_curve(1, 1)
        self.assertEqual(len(ui.state()['impedances']), 0)
        self.assertEqual(len(ui.state()['curves']), 2)

    def test_failed_upload_keeps_valid_data(self):
        self.memory['file'] = self.file()
        ui.upload_lsv(1, 1, 'file')
        before = ui.find_curve(1, 1)['text']
        self.memory['file'] = Upload('invalido.txt', 'não há dados')
        ui.upload_lsv(1, 1, 'file')
        self.assertEqual(ui.find_curve(1, 1)['text'], before)
        self.assertIn('invalido.txt', self.memory['lsv_error'])

    def test_session_invalid_does_not_replace_current(self):
        self.memory['session'] = Upload('bad.json', '[]')
        ui.load_uploaded_session('session')
        self.assertEqual(ui.state()['samples'][0]['name'], 'Amostra 1')
        self.assertIn('Não foi possível', self.memory['lsv_error'])


if __name__ == '__main__':
    unittest.main()
