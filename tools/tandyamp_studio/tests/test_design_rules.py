"""Check prospective musical design contract and reference fingerprints.

This does not implement a genre engine, change defaults or distribute MIDI.
"""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'benchmarks'


class MusicalDesignDocsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((DATA/'design_rules.json').read_text(encoding='utf-8'))

    def test_spec_is_explicitly_design_only_and_minimal(self):
        self.assertEqual(self.spec['status'], 'design_only_not_implemented')
        self.assertTrue(self.spec['use_one_arranger'])
        self.assertFalse(self.spec['permanent_genre_specific_engines'])
        self.assertEqual(self.spec['roles'],
                         ['foundation','identity','useful_support'])
        self.assertIn('simplest MIDI', self.spec['goal'])

    def test_hardware_constraints_remain_real(self):
        hw = self.spec['hardware']
        self.assertEqual((hw['psg_pitched_voices'],
                          hw['psg_noise_voices'],
                          hw['optional_spk4_bass_voices']), (3,1,1))
        self.assertLess(hw['studio_target_max_bytes'],
                        hw['dos_max_input_bytes'])
        self.assertEqual(hw['format_type'], 0)

    def test_reference_documents_and_hashes(self):
        required = {'seventh_son','brandenburg','demo'}
        found = set()
        for item in self.spec['benchmarks']:
            found.add(item['name'])
            self.assertTrue((DATA/item['path']).is_file())
            self.assertRegex(item['sha256'], r'^[0-9a-f]{64}$')
            self.assertIn(item['sha256'],
                          (DATA/item['path']).read_text(encoding='utf-8'))
            self.assertGreater(item['notes'], 0)
        self.assertEqual(found, required)

    def test_defaults_max_raw_and_separate_output(self):
        self.assertTrue(self.spec['baseline']['must_remain_unchanged'])
        self.assertFalse(self.spec['max_raw']['default'])
        self.assertTrue((ROOT/'defaults.py').exists())
        rules = (ROOT/'DESIGN_RULES.md').read_text(encoding='utf-8')
        self.assertIn('simplest MIDI', rules)
        self.assertIn('not implemented', rules.lower())


if __name__ == '__main__':
    unittest.main()
