"""The hardware-approved pitch-arrangement profile and the Build 56 recipe."""
from types import MappingProxyType

BUILD56_DEFAULTS = MappingProxyType({
    'preset': 'balanced',
    'spk4': 'adapt',
    'stems': False,  # guitar_separation=True implies six-stem separation
    'preview': True,
    'drum_style': 'rock',
    'note_preservation': 'full',
    'guitar_separation': True,
    'accompaniment': 'off',
    'transcription': 'sensitive',
    'voice_selection': 'smart',
    'max_raw': False,
    'mp3_quality': '192',
})

BUILD56_REFERENCE_MIDI_SHA256 = (
    'c8f9c342a7632ac50df52f8eb6f4c26e0dc56e42c001ef52a5b7b9a1a606ad5f'
)

STUDIO_DEFAULTS = MappingProxyType({
    **BUILD56_DEFAULTS,
    'arrangement': 'tuned',
    'core_smoothing': 'auto',
    'spk4': 'off',
})

PARATUNE_REFERENCE_MIDI_SHA256 = (
    'b805d921db12b81f2575921fb49b29adb173997a52ac16e9c82bb50f42742b65'
)
