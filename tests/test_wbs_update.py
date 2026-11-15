import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('wbs_update', ROOT/'scripts/update-wbs.py')
wbs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wbs)


class WbsUpdateTests(unittest.TestCase):
    def test_empty_cell_replacement_does_not_consume_following_row(self):
        xml='<worksheet><row r="17"><c r="M17" s="19"/></row><row r="18"><c r="A18"><v>2</v></c></row></worksheet>'
        updated=wbs.put(xml,'M17','evidence')
        self.assertIn('<row r="18">',updated)
        self.assertIn('<c r="A18"><v>2</v></c>',updated)

    def test_real_workbook_preserves_owners_progress_dates_and_all_40_tasks(self):
        original=ROOT/'docs/wbs/original-11week.xlsx'
        entries=json.loads((ROOT/'docs/wbs/task-evidence.json').read_text(encoding='utf-8'))['tasks']
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'reviewed.xlsx'; audit=Path(directory)/'audit.json'
            wbs.update(original,entries,output,audit)
            with zipfile.ZipFile(original) as src, zipfile.ZipFile(output) as dst:
                self.assertIsNone(dst.testzip())
                shared=[''.join(n.itertext()) for n in ET.fromstring(src.read('xl/sharedStrings.xml')).findall('s:si',wbs.NS)]
                before=wbs.cells(src.read('xl/worksheets/sheet2.xml'),shared)
                after=wbs.cells(dst.read('xl/worksheets/sheet2.xml'),shared)
                for row in range(17,57):
                    for col in ['A','C','D','F','G','I']:
                        self.assertEqual(before[f'{col}{row}'],after[f'{col}{row}'])
                self.assertEqual(after['P4'],'40')
                self.assertEqual(after['E27'],'팀장 / 보안 검사·정책')
                for name in ['xl/worksheets/sheet1.xml','xl/worksheets/sheet2.xml','xl/worksheets/sheet4.xml']:
                    document=ET.fromstring(dst.read(name))
                    for row in document.findall('.//s:row',wbs.NS):
                        refs=[c.attrib['r'] for c in row.findall('s:c',wbs.NS)]
                        self.assertEqual(len(refs),len(set(refs)))
                for name in src.namelist():
                    if any(x in name for x in ['/drawings/','/media/','/charts/']):
                        self.assertEqual(src.read(name),dst.read(name))
            self.assertFalse(json.loads(audit.read_text(encoding='utf-8'))['numeric_progress_changed'])
            with self.assertRaises(ValueError): wbs.update(original,entries,output,audit)
