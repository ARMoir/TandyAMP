#!/usr/bin/env python3
"""Check TandyAMP Markdown docs against implementation and GitHub release policy.

Only Python's standard library is used. Intended for the repository root.
"""
from pathlib import Path
import re
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    ROOT / "README.md",
    *sorted((ROOT / "docs").glob("*.md")),
]
CODE = (ROOT / "src/main.c").read_text(encoding="utf-8")
MIDI = (ROOT / "src/midi.h").read_text(encoding="utf-8")
MIDI_SOURCE = (ROOT / "src/midi.c").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/build-dos.yml").read_text(encoding="utf-8")
README = FILES[0].read_text(encoding="utf-8")
ARCH = (ROOT / "docs/PLAYER_ARCHITECTURE.md").read_text(encoding="utf-8")
UI = (ROOT / "docs/UI_DESIGN.md").read_text(encoding="utf-8")
errors = []

def demand(ok, message):
    if not ok:
        errors.append(message)

# Every relative link must point to an actual checked-in file or directory.
# External URLs and headings are intentionally out of scope.
for path in FILES:
    text = path.read_text(encoding="utf-8")
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        target = unquote(target.split("#", 1)[0].strip())
        if not target or target.startswith(("https://", "http://", "mailto:")):
            continue
        location = (path.parent / target).resolve()
        demand(location.exists(), f"{path.relative_to(ROOT)}: broken link {target}")

demand(len(FILES) >= 6, "Expected README and at least five documentation pages")
demand("#define MAX_SONGS 64" in CODE and "64" in README, "Playlist capacity undocumented")
demand("#define PATHLEN 64" in CODE and "63 characters" in README, "Filename limit undocumented")
demand("#define TA_MAX_TRACKS 24" in MIDI and "24" in README, "Track limit undocumented")
demand("#define TA_MAX_FILE 45056U" in MIDI and "45,056" in README, "44 KiB file limit undocumented")
demand("#define UI_BUTTON_COUNT 10U" in CODE and "ten" in UI,
       "Ten-button control count mismatch")
demand("#define UI_BUTTON_COLS 5U" in CODE and "two" in UI,
       "Two even rows of five missing")
demand('"/SPK4"' in CODE and '"/NOSPK4"' in CODE, "Missing speaker CLI options")
demand("ta_set_speaker" in CODE and "SPK4" in README, "Speaker toggle undocumented")
demand("#define UI_BUTTON_HEIGHT 17U" in CODE and "58×17" in UI,
       "58×17 control dimensions inconsistent")
demand("case 'M':" in CODE and "else if(id==9)input_key('M')" in CODE,
       "Mute keyboard or mouse action missing")
demand("TA_SPK_BASS_MIN 24" in MIDI_SOURCE and "TA_SPK_BASS_MAX 52" in MIDI_SOURCE
       and "24–52" in README, "SPK4 bass-only note range undocumented")
demand("speaker_divider_for" in MIDI_SOURCE and "1.193182" in README,
       "PIT2 true-octave note mapping undocumented")
demand("UI_METER_COUNT 4U" in CODE and "four-column" in README,
       "Four-column real-output monitor undocumented")
demand("ta.speaker_divider" in CODE and "speaker_divider" in MIDI,
       "PIT2 actual activity telemetry missing")
demand("white-on-black" in UI and "box(7,187,306,10,0)" in CODE,
       "EX contrast fix not documented or implemented")
demand("#define UI_BUTTON_WIDTH 58U" in CODE and "58×17 pixels" in UI,
       "Two-row button width mismatch")
demand("playlist_find_current_directory" in CODE and "current working directory" in README,
       "Automatic MIDI directory discovery undocumented")
demand("mouse_cursor_draw" in CODE and "/NOMOUSE" in README,
       "Mouse pointer and fallback undocumented")
demand("TA_DRUM_AUTO" in MIDI and "/AUTODRUM16" in README,
       "Drum auto-detection undocumented")
demand("ta_set_volume" in CODE and "/VOL:0..20" in README,
       "Master 0–20 volume option undocumented")
demand("TA_MIX_POWER_CEILING 6144U" in MIDI_SOURCE and "6,144" in README,
       "Loudness/limiter ceiling undocumented")
demand("TA_MAX_VOLUME 20U" in MIDI_SOURCE and "volume>20" in CODE,
       "Master boosted volume range mismatch")
demand("timer_start" in CODE and "mode 2" in ARCH,
       "PIT scheduling undocumented")
demand("tests/check_docs.py" in README and "tests/check_docs.py" in WORKFLOW,
       "Documentation verifier absent from build guide/workflow")
demand("TANDYAMP.EXE DEMO.MID LICENSE" in WORKFLOW,
       "Runtime ZIP contents have changed: update documentation")
demand("No Markdown files in the DOS ZIP" in WORKFLOW,
       "ZIP exclusion statement missing")
demand("tandyamp-build-" in README and "gh release create" in WORKFLOW,
       "Release naming/publishing documentation mismatch")
demand("gh release delete" in WORKFLOW and "previous" in README,
       "Release cleanup documentation mismatch")
demand("not" in README.lower() and "physical EX" in README,
       "Missing hardware verification caveat")
if errors:
    print("Documentation check FAILED:")
    for item in errors:
        print(" -", item)
    sys.exit(1)
print("PASS: documentation links, CLI, limits, mouse, playback and release policy")
