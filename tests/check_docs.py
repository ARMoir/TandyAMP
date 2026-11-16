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
demand("#define UI_BUTTON_COUNT 9U" in CODE and "ninth" in UI, "Button count mismatch")
demand("UI_ROW_BUTTONS 8U" in CODE, "Transport row geometry changed")
demand('"/SPK4"' in CODE and '"/NOSPK4"' in CODE, "Missing speaker CLI options")
demand("ta_set_speaker" in CODE and "SPK4" in README, "Speaker toggle undocumented")
demand("#define UI_BUTTON_WIDTH 36U" in CODE and "36-pixel" in UI, "Button width mismatch")
demand("playlist_find_current_directory" in CODE and "current working directory" in README,
       "Automatic MIDI directory discovery undocumented")
demand("mouse_cursor_draw" in CODE and "/NOMOUSE" in README,
       "Mouse pointer and fallback undocumented")
demand("TA_DRUM_AUTO" in MIDI and "/AUTODRUM16" in README,
       "Drum auto-detection undocumented")
demand("ta_set_volume" in CODE and "/VOL:0..15" in README,
       "Master volume option undocumented")
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
