"""Regression tests for Basic Pitch dependency diagnostics and model invocation."""
from __future__ import annotations

from pathlib import Path
import builtins
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from transcribe import _predict


class BasicPitchTests(unittest.TestCase):
    def test_predict_receives_required_model_path(self):
        package = types.ModuleType('basic_pitch')
        package.ICASSP_2022_MODEL_PATH = 'test-model.onnx'
        inference = types.ModuleType('basic_pitch.inference')
        seen = {}

        def fake_predict(audio, model):
            seen['audio'] = audio
            seen['model'] = model
            note = types.SimpleNamespace(start=0.0, end=.5, pitch=60, velocity=95)
            instrument = types.SimpleNamespace(notes=[note])
            return {}, types.SimpleNamespace(instruments=[instrument]), []

        inference.predict = fake_predict
        with patch.dict(sys.modules, {'basic_pitch': package, 'basic_pitch.inference': inference}):
            notes = _predict(Path('example.mp3'), 'melody')
        self.assertEqual(seen, {'audio': 'example.mp3', 'model': 'test-model.onnx'})
        self.assertEqual(len(notes), 1)
        self.assertEqual((notes[0].pitch, notes[0].part), (60, 'melody'))

    def test_actual_missing_pkg_resources_reported(self):
        original_import = builtins.__import__

        def broken_import(name, *args, **kwargs):
            if name == 'basic_pitch.inference':
                raise ModuleNotFoundError("No module named 'pkg_resources'",
                                            name='pkg_resources')
            return original_import(name, *args, **kwargs)

        package = types.ModuleType('basic_pitch')
        package.ICASSP_2022_MODEL_PATH = 'test-model.onnx'
        with patch.dict(sys.modules, {'basic_pitch': package}):
            with patch('builtins.__import__', side_effect=broken_import):
                with self.assertRaisesRegex(RuntimeError, 'setuptools 82'):
                    _predict(Path('example.mp3'), None)

    def test_missing_basic_pitch_has_install_command(self):
        with patch.dict(sys.modules, {'basic_pitch': None}):
            with self.assertRaisesRegex(RuntimeError, 'requirements-audio.txt'):
                _predict(Path('example.mp3'), None)

    def test_other_dependency_name_is_preserved(self):
        original_import = builtins.__import__

        def broken_import(name, *args, **kwargs):
            if name == 'basic_pitch.inference':
                raise ModuleNotFoundError("No module named 'unexpected_ml_runtime'",
                                            name='unexpected_ml_runtime')
            return original_import(name, *args, **kwargs)

        package = types.ModuleType('basic_pitch')
        package.ICASSP_2022_MODEL_PATH = 'test-model.onnx'
        with patch.dict(sys.modules, {'basic_pitch': package}):
            with patch('builtins.__import__', side_effect=broken_import):
                with self.assertRaisesRegex(RuntimeError, 'unexpected_ml_runtime'):
                    _predict(Path('example.mp3'), None)


if __name__ == '__main__':
    unittest.main()
