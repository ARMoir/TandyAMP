"""Verified default Studio recipe from Paranoid_SPK4_Build56.zip.

The package's PARANOID.MID has MIDI channel 0 CC119=77, proving it
requests SMART voice selection. The original conversion command used:
  --preset balanced --guitar-separation --transcription sensitive
  --note-preservation full --voice-selection smart --spk4 adapt
  --drum-style rock --accompaniment off --preview
The missing --stems flag is intentional: guitar_separation implies
six-stem Demucs in transcribe_audio(). The WAV preview flag only affects
the optional diagnostic audio; it does not alter generated MIDI notes.
Do not confuse these options with the DOS Build56 PLAY.BAT /SPK4:ADAPT.
MAX RAW stays a separately selected override, not the default.
"""
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
