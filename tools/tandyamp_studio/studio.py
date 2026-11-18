"""TandyAMP Studio: local MIDI/audio or YouTube -> SPK4-aware DOS MIDI."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import tempfile
from typing import TYPE_CHECKING

from arranger import PRESETS, export, load_midi, prepare, voice_coverage
from defaults import STUDIO_DEFAULTS as DEFAULTS
from dependencies import ffmpeg_help, install_ffmpeg_windows, missing_ffmpeg
from youtube import cached_youtube_mp3, download_youtube_mp3, is_youtube_url, safe_name

if TYPE_CHECKING:
    from pitch_arranger import Reference

ARRANGEMENTS = {
    'tuned': '_TUNED', 'classic': '_TANDY', 'musical': '_MUSIC', 'core': '_CORE',
}


def _default_arrangement(source: str, max_raw: bool = False) -> str:
    if max_raw or (not is_youtube_url(source)
                   and Path(source).suffix.lower() in ('.mid', '.midi')):
        return 'classic'
    return DEFAULTS['arrangement']


def _convert_local(input_file: Path, output_dir: Path, target_name: str,
                   preset: str, spk4: str, stems: bool, preview: bool,
                   saved_mp3: Path | None = None,
                   drum_style: str = DEFAULTS['drum_style'],
                   note_preservation: str = DEFAULTS['note_preservation'],
                   guitar_separation: bool = DEFAULTS['guitar_separation'],
                   accompaniment: str = DEFAULTS['accompaniment'],
                   transcription: str = DEFAULTS['transcription'],
                   voice_selection: str = DEFAULTS['voice_selection'],
                   max_raw: bool = DEFAULTS['max_raw'],
                   arrangement: str = DEFAULTS['arrangement'],
                   core_smoothing: str = DEFAULTS['core_smoothing'],
                   reference: Reference | None = None) -> list[Path]:
    audio_input = input_file.suffix.lower() in ('.mp3', '.wav', '.flac', '.ogg')
    phrase_score = None
    evidence = None
    pitch_report = None
    if input_file.suffix.lower() in ('.mid', '.midi'):
        if max_raw:
            raise ValueError('MAX RAW is for YouTube/audio transcription, not existing MIDI files')
        if reference is not None:
            raise ValueError('A reference MIDI guides an audio or YouTube input')
        print(f'Loading MIDI: {input_file}', flush=True)
        notes = load_midi(input_file)
    elif audio_input:
        from transcribe import transcribe_audio
        print(f'Transcribing audio: {input_file}', flush=True)
        transcribe_kwargs = dict(stems=stems, drum_style=drum_style,
                                 preservation=note_preservation,
                                 guitar_separation=guitar_separation,
                                 accompaniment=accompaniment, profile=transcription)
        if max_raw:
            transcribe_kwargs['raw_mode'] = True
            print('MAX RAW: high-recall six-stem transcription including piano; '
                  'no note filtering or automatic leveling.', flush=True)
        elif arrangement in ('core', 'tuned'):
            from phrase_score import ScoreEvidence
            evidence = ScoreEvidence()
            transcribe_kwargs['score_evidence'] = evidence
        notes = transcribe_audio(input_file, **transcribe_kwargs)
    else:
        raise ValueError('Input must be MID, MIDI, MP3, WAV, FLAC, OGG, or a YouTube video URL')
    print(f'Extracted {len(notes)} note events', flush=True)
    keep_candidates = (not max_raw and arrangement == 'classic' and
                       note_preservation == 'full' and
                       (audio_input or voice_selection == 'smart'))
    music_report = None
    if max_raw:
        arranged = list(notes)
    elif evidence is not None:
        from phrase_score import arrange_score, reconstruct_score
        phrase_score = reconstruct_score(notes, evidence,
                                         connect=core_smoothing != 'off')
        if arrangement == 'tuned':
            from pitch_arranger import arrange_tuned
            arranged, pitch_report = arrange_tuned(phrase_score, notes, preset, reference)
            print(pitch_report.as_text(), end='', flush=True)
        else:
            arranged = arrange_score(phrase_score, preset)
    elif arrangement in ('musical', 'core'):
        from arranger import normalize
        from musical_arranger import arrange_musically
        # Preserve credible note attacks and original timing before making
        # the *offline* three-tone (+ eligible SPK4) arrangement.
        candidates = normalize(notes, preset, preserve=True)
        if arrangement == 'core':
            from core_arranger import arrange_core
            smooth = core_smoothing == 'on'
            arranged, music_report = arrange_core(candidates, spk4=spk4,
                                                 smooth=smooth)
            print('CORE smoothing: {} (same-pitch holds, small legato joins, '
                  'weak A-B-A pitch spike cleanup).'.format(
                      'enabled' if smooth else 'disabled'), flush=True)
        else:
            arranged, music_report = arrange_musically(candidates, spk4=spk4)
    else:
        arranged = prepare(notes, preset, spk4,
                           preserve=keep_candidates,
                           voice_selection=voice_selection)
    if keep_candidates:
        print('Full mode preserves up to six MIDI candidates at once; '
              'TandyAMP still plays at most three PSG tones plus '
              'an eligible SPK4 bass.', flush=True)
    if max_raw:
        print(f'MAX RAW: exporting all {len(arranged)} detected events, '
              'unaltered. No voice cap, velocity floor or pitch folding.',
              flush=True)
    elif phrase_score is not None:
        print(f'{arrangement.upper()}: built {len(phrase_score.phrases)} phrases before '
              f'PSG allocation ({len(arranged)} output events).', flush=True)
    elif music_report is not None:
        print('{}: selected {} original pitched notes, produced {} '
              'pitched fragments and {} drum hits from {} source events.'
              .format(arrangement.upper(), music_report.retained_source_notes if
                      arrangement == 'core' else music_report.selected_source_notes,
                      music_report.chosen_pitched if arrangement == 'core'
                      else music_report.output_pitched_fragments,
                      music_report.chosen_drums if arrangement == 'core'
                      else music_report.output_drums, len(notes)), flush=True)
    else:
        print(f'Arranged {len(arranged)} events for Tandy PSG + SPK4 {spk4}', flush=True)
    if voice_selection == 'smart' and not max_raw:
        print('Smart riff-protected voice selection enabled in MIDI (CC119=77). '
              'Requires the latest TANDYAMP.EXE build for real DOS playback.',
              flush=True)
    inferred = [n for n in arranged if n.part == 'accomp']
    if audio_input and reference is None:
        print('  Original/AI pitched notes: {}; inferred accompaniment: {}'.format(
            sum(n.part not in ('drums', 'accomp') for n in arranged),
            len(inferred)), flush=True)
    for title, sample in (() if max_raw else
                          (('Input after transcription', notes),
                           ('MIDI candidate output', arranged))):
        cov = voice_coverage(sample)
        print('  {}: silent {:.1f}s, one tone {:.1f}s, two {:.1f}s, '
              'three+ {:.1f}s, four+ {:.1f}s, bass only {:.1f}s; '
              'potential 4-voice SPK4 {:.1f}s'.format(
                  title, cov['silent'], cov['one'], cov['two'],
                  cov['three_plus'], cov['four_plus'], cov['bass_only'],
                  cov['four_candidate']), flush=True)
    # Diagnostic counts help identify the "all kicks" / "all bass velocity
    # 107" regressions without requiring music uploads for every conversion.
    from collections import Counter
    drums = Counter(n.pitch for n in arranged if n.part == 'drums')
    bass_velocities = [n.velocity for n in arranged if n.part == 'bass']
    if drums:
        print('  Drums: kick={} snare={} hat={}'.format(
            drums[36], drums[38], drums[42]), flush=True)
        if max(drums.values()) / sum(drums.values()) > .88 and sum(drums.values()) > 25:
            print('  WARNING: one drum type dominates; classification may be unreliable.',
                  flush=True)
    if bass_velocities:
        print('  Bass: {} notes, velocity range {}..{}, {} distinct levels'.format(
            len(bass_velocities), min(bass_velocities), max(bass_velocities),
            len(set(bass_velocities))), flush=True)
    folder_suffix = ARRANGEMENTS[arrangement]
    target = output_dir / (target_name + folder_suffix)
    if saved_mp3 is not None and (target / 'SOURCE.MP3').exists():
        raise FileExistsError(f'Refusing to overwrite existing SOURCE.MP3 in {target}')
    if max_raw:
        from max_raw import export_raw, raw_summary
        files = export_raw(arranged, target)
        (target / 'MAXRAW.TXT').write_text(raw_summary(arranged), encoding='ascii')
    else:
        files = export(arranged, target, voice_selection=voice_selection)
        from diagnostics import save_stage
        save_stage(target, 'INPUT', notes, spk4=spk4, voice_selection=voice_selection)
        save_stage(target, 'METRICS', arranged, spk4=spk4, voice_selection=voice_selection)
        if phrase_score is not None:
            from dataclasses import asdict
            from diagnostics import write_json
            write_json(target / 'SCORE.json', asdict(phrase_score))
            (target / 'CORE.TXT').write_text(phrase_score.summary(), encoding='ascii')
        if pitch_report is not None:
            (target / 'PITCH.TXT').write_text(pitch_report.as_text(), encoding='ascii')
        elif music_report is not None:
            report_name = 'CORE.TXT' if arrangement == 'core' else 'MUSIC.TXT'
            (target / report_name).write_text(music_report.as_text(),
                                              encoding='ascii')
    if audio_input and accompaniment != 'off' and not max_raw and reference is None:
        report = ('TandyAMP Studio accompaniment provenance\n'
                  'Separation: {}\nAccompaniment: {}\n'
                  'Inferred support events: {}\n'
                  'Note source: guitar/other spectral chord evidence; '
                  'not Basic Pitch transcription.\n'
                  'MIDI channel: 4 (zero-based 3).\n'
                  'Player: 3 PSG tones + optional independent PIT2 bass.\n'
                  .format('htdemucs_6s' if guitar_separation else 'htdemucs',
                          accompaniment, len(inferred)))
        (target / 'ARRANGE.TXT').write_text(report, encoding='ascii')
    for f in files:
        print(f'  {f.name} ({f.stat().st_size} bytes)', flush=True)
    playmode = {'off': '/NOSPK4', 'bass': '/SPK4', 'adapt': '/SPK4:ADAPT'}[spk4]
    (target / 'PLAY.BAT').write_bytes(('@ECHO OFF\r\nTANDYAMP ' + playmode + '\r\n').encode('ascii'))
    if preview:
        from preview import preview_wav
        wav = preview_wav(arranged, target / 'PREVIEW.WAV', spk4=spk4,
                          voice_selection='legacy' if max_raw else voice_selection)
        print(f'Approximate 30-second square-wave preview: {wav}', flush=True)
        if phrase_score is not None:
            for name, parts in (
                ('RHYTHM', ('bass', 'drums')),
                ('RIFF', ('bass', 'drums', 'guitar', 'harmony', 'accomp')),
            ):
                layer = [n for n in arranged if n.part in parts]
                if layer:
                    preview_wav(layer, target / 'AUDITION' / (name + '.WAV'),
                                spk4=spk4, voice_selection=voice_selection)
    if saved_mp3 is not None:
        shutil.copyfile(saved_mp3, target / 'SOURCE.MP3')
        print(f'Kept original MP3: {target / "SOURCE.MP3"}', flush=True)
    print(f'Complete. Copy MID files and PLAY.BAT from {target} to your DOS CF card.', flush=True)
    return files


def convert(input_file: str | Path, output_dir: Path,
            preset: str = DEFAULTS['preset'],
            spk4: str = DEFAULTS['spk4'],
            stems: bool = DEFAULTS['stems'],
            preview: bool = DEFAULTS['preview'],
            *, keep_mp3: bool = False, mp3_only: bool = False,
            mp3_quality: str = DEFAULTS['mp3_quality'],
            drum_style: str = DEFAULTS['drum_style'],
            note_preservation: str = DEFAULTS['note_preservation'],
            guitar_separation: bool = DEFAULTS['guitar_separation'],
            accompaniment: str = DEFAULTS['accompaniment'],
            transcription: str = DEFAULTS['transcription'],
            voice_selection: str = DEFAULTS['voice_selection'],
            max_raw: bool = DEFAULTS['max_raw'],
            arrangement: str | None = DEFAULTS['arrangement'],
            core_smoothing: str = DEFAULTS['core_smoothing'],
            reference_midi: Path | None = None,
            reference_channels: str | None = None,
            reference_alignment: str | None = None,
            reference_end: float | None = None) -> list[Path]:
    """Convert audio with Tuned by default and reuse a cached YouTube MP3."""
    if preset not in PRESETS:
        raise ValueError(f'Unknown preset: {preset}')
    if spk4 not in ('off', 'bass', 'adapt'):
        raise ValueError(f'Unknown SPK4 mode: {spk4}')
    if drum_style not in ('auto', 'rock'):
        raise ValueError(f'Unknown drum style: {drum_style}')
    if note_preservation not in ('full', 'clean'):
        raise ValueError(f'Unknown note preservation: {note_preservation}')
    if accompaniment not in ('off', 'recover', 'harmonize'):
        raise ValueError(f'Unknown accompaniment mode: {accompaniment}')
    if transcription not in ('standard', 'sensitive'):
        raise ValueError('Unknown transcription profile: ' + transcription)
    if voice_selection not in ('legacy', 'smart'):
        raise ValueError('Voice selection must be legacy or smart')
    if arrangement is not None and arrangement not in ARRANGEMENTS:
        raise ValueError(f'Unknown arrangement: {arrangement}')
    if max_raw and arrangement not in (None, 'classic', DEFAULTS['arrangement']):
        raise ValueError('MAX RAW and arranged modes are alternative output modes')
    if core_smoothing not in ('auto', 'on', 'off'):
        raise ValueError('CORE smoothing must be auto, on or off')
    if max_raw and mp3_only:
        raise ValueError('MAX RAW creates MIDI, so it cannot be combined with --mp3-only')
    arrangement = 'classic' if max_raw else arrangement or DEFAULTS['arrangement']
    reference = None
    if reference_midi is not None:
        if arrangement != 'tuned' or mp3_only:
            raise ValueError('A reference MIDI requires the Tuned audio arrangement')
        from pitch_arranger import BeatGrid, Reference
        grid = BeatGrid.parse(reference_alignment) if reference_alignment else None
        reference = Reference.load(Path(reference_midi).expanduser(), reference_channels,
                                   grid, reference_end)
    elif any(v is not None for v in (reference_channels, reference_alignment, reference_end)):
        raise ValueError('Reference settings require --reference-midi')
    source = str(input_file).strip()
    if not source:
        raise ValueError('Provide a music file or YouTube video URL')
    output_dir = Path(output_dir).expanduser().resolve()
    options = dict(drum_style=drum_style, note_preservation=note_preservation,
                   guitar_separation=guitar_separation, accompaniment=accompaniment,
                   transcription=transcription, voice_selection=voice_selection,
                   arrangement=arrangement)
    if max_raw:
        options['max_raw'] = True
    if core_smoothing != DEFAULTS['core_smoothing']:
        options['core_smoothing'] = core_smoothing
    if reference is not None:
        options['reference'] = reference
    if is_youtube_url(source):
        with tempfile.TemporaryDirectory(prefix='tandyamp-youtube-') as temp:
            downloaded = download_youtube_mp3(source, Path(temp), mp3_quality)
            name = safe_name(downloaded.title, downloaded.video_id)
            if mp3_only:
                output_dir.mkdir(parents=True, exist_ok=True)
                destination = output_dir / (name + '.mp3')
                if destination.exists():
                    raise FileExistsError(f'Refusing to overwrite {destination}')
                shutil.copyfile(downloaded.audio_path, destination)
                print(f'MP3 saved: {destination}', flush=True)
                return [destination]
            return _convert_local(downloaded.audio_path, output_dir, name,
                                  preset, spk4, stems, preview,
                                  saved_mp3=downloaded.audio_path if keep_mp3 else None,
                                  **options)
    if source.lower().startswith(('http://', 'https://')):
        raise ValueError('Only single-video YouTube links are supported (https://youtu.be/... or youtube.com/watch?v=...)')
    if keep_mp3 or mp3_only:
        raise ValueError('--keep-mp3 and --mp3-only apply to YouTube URLs only')
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() in ('.mid', '.midi') and not max_raw and arrangement == 'tuned':
        # An authored MIDI already specifies its intended pitches.
        if reference is not None:
            raise ValueError('A reference MIDI guides an audio or YouTube input')
        options['arrangement'] = 'classic'
    return _convert_local(path, output_dir, path.stem, preset, spk4, stems, preview,
                          **options)


def gui(initial_input: str = '', *, initial_output: Path | None = None) -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from concurrent.futures import ThreadPoolExecutor

    try:
        from tkinterdnd2 import TkinterDnD, DND_FILES
        root = TkinterDnD.Tk()
    except ImportError:
        root = tk.Tk()
        DND_FILES = None

    root.title('TandyAMP Studio - YouTube / MP3 / MIDI to Tandy DOS')
    root.geometry('710x735')
    root.minsize(625, 675)
    path = tk.StringVar(value=initial_input)
    output = tk.StringVar(value=str(initial_output or Path.home() / 'Music'))
    preset = tk.StringVar(value=DEFAULTS['preset'])
    spk4 = tk.StringVar(value=DEFAULTS['spk4'])
    drum_style = tk.StringVar(value=DEFAULTS['drum_style'])
    note_preservation = tk.StringVar(value=DEFAULTS['note_preservation'])
    guitar_separation = tk.BooleanVar(value=DEFAULTS['guitar_separation'])
    accompaniment = tk.StringVar(value=DEFAULTS['accompaniment'])
    transcription = tk.StringVar(value=DEFAULTS['transcription'])
    voice_selection = tk.StringVar(value=DEFAULTS['voice_selection'])
    arrangement = tk.StringVar(value=DEFAULTS['arrangement'])
    core_smoothing = tk.StringVar(value=DEFAULTS['core_smoothing'])
    max_raw = tk.BooleanVar(value=DEFAULTS['max_raw'])
    stems = tk.BooleanVar(value=DEFAULTS['stems'])
    preview = tk.BooleanVar(value=DEFAULTS['preview'])
    keep_mp3 = tk.BooleanVar(value=False)
    mp3_only = tk.BooleanVar(value=False)
    message = tk.StringVar(value='Paste a single YouTube video URL or select a MIDI/audio file.')
    outer = ttk.Frame(root, padding=16)
    outer.pack(fill='both', expand=True)
    outer.columnconfigure(1, weight=1)
    ttk.Label(outer, text='File / YouTube URL').grid(row=0, column=0, sticky='w', pady=7)
    ttk.Entry(outer, textvariable=path).grid(row=0, column=1, sticky='ew', padx=8)
    ttk.Button(outer, text='Browse...', command=lambda: path.set(filedialog.askopenfilename(filetypes=[('Music', '*.mid *.midi *.mp3 *.wav *.flac *.ogg'), ('All files', '*.*')]) or path.get())).grid(row=0, column=2)
    ttk.Label(outer, text='Output folder').grid(row=1, column=0, sticky='w', pady=7)
    ttk.Entry(outer, textvariable=output).grid(row=1, column=1, sticky='ew', padx=8)
    ttk.Button(outer, text='Browse...', command=lambda: output.set(filedialog.askdirectory() or output.get())).grid(row=1, column=2)
    ttk.Label(outer, text='Preset').grid(row=2, column=0, sticky='w', pady=7)
    ttk.Combobox(outer, textvariable=preset, values=list(PRESETS), state='readonly', width=19).grid(row=2, column=1, sticky='w', padx=8)
    ttk.Label(outer, text='SPK4').grid(row=3, column=0, sticky='w', pady=7)
    ttk.Combobox(outer, textvariable=spk4, values=['off', 'bass', 'adapt'], state='readonly', width=19).grid(row=3, column=1, sticky='w', padx=8)
    ttk.Label(outer, text='Drums').grid(row=4, column=0, sticky='w', pady=6)
    ttk.Combobox(outer, textvariable=drum_style, values=['auto', 'rock'], state='readonly', width=19).grid(row=4, column=1, sticky='w', padx=8)
    ttk.Label(outer, text='Notes').grid(row=5, column=0, sticky='w', pady=6)
    ttk.Combobox(outer, textvariable=note_preservation, values=['full', 'clean'], state='readonly', width=19).grid(row=5, column=1, sticky='w', padx=8)
    ttk.Checkbutton(outer, text='Separate MP3/WAV stems (Demucs, slower)', variable=stems).grid(row=6, column=0, columnspan=3, sticky='w', pady=2)
    ttk.Checkbutton(outer, text='Isolate guitar (6-stem Demucs, extra model download)', variable=guitar_separation).grid(row=7, column=0, columnspan=3, sticky='w', pady=2)
    ttk.Label(outer, text='Accompaniment').grid(row=8, column=0, sticky='w', pady=6)
    ttk.Combobox(outer, textvariable=accompaniment, values=['off', 'recover', 'harmonize'], state='readonly', width=19).grid(row=8, column=1, sticky='w', padx=8)
    ttk.Label(outer, text='Transcription').grid(row=9, column=0, sticky='w', pady=6)
    ttk.Combobox(outer, textvariable=transcription, values=['standard', 'sensitive'], state='readonly', width=19).grid(row=9, column=1, sticky='w', padx=8)
    ttk.Label(outer, text='Voices').grid(row=10, column=0, sticky='w', pady=6)
    ttk.Combobox(outer, textvariable=voice_selection, values=['legacy', 'smart'], state='readonly', width=19).grid(row=10, column=1, sticky='w', padx=8)
    ttk.Label(outer, text='Arrangement').grid(row=11, column=0, sticky='w', pady=6)
    ttk.Combobox(outer, textvariable=arrangement, values=list(ARRANGEMENTS), state='readonly', width=19).grid(row=11, column=1, sticky='w', padx=8)
    ttk.Label(outer, text='CORE smoothing').grid(row=12, column=0, sticky='w', pady=6)
    ttk.Combobox(outer, textvariable=core_smoothing, values=['auto', 'on', 'off'], state='readonly', width=19).grid(row=12, column=1, sticky='w', padx=8)
    ttk.Checkbutton(outer, text='MAX RAW (YouTube/audio: all six stems, all detected notes, no leveling)',
                    variable=max_raw,
                    command=lambda: arrangement.set('classic' if max_raw.get()
                                                    else DEFAULTS['arrangement'])).grid(row=13, column=0, columnspan=3, sticky='w', pady=2)
    ttk.Checkbutton(outer, text='Generate approximate WAV preview', variable=preview).grid(row=14, column=0, columnspan=3, sticky='w', pady=2)
    ttk.Checkbutton(outer, text='Keep downloaded YouTube MP3 alongside MIDI', variable=keep_mp3).grid(row=15, column=0, columnspan=3, sticky='w', pady=2)
    ttk.Checkbutton(outer, text='MP3 only: download audio, skip MIDI transcription', variable=mp3_only).grid(row=16, column=0, columnspan=3, sticky='w', pady=2)
    status = ttk.Label(outer, textvariable=message, wraplength=660)
    status.grid(row=18, column=0, columnspan=3, sticky='w', pady=8)
    if DND_FILES:
        root.drop_target_register(DND_FILES)
        root.dnd_bind('<<Drop>>', lambda event: path.set(root.tk.splitlist(event.data)[0]))
    pool = ThreadPoolExecutor(max_workers=1)

    def offer_ffmpeg_install() -> None:
        missing = missing_ffmpeg()
        if not missing:
            messagebox.showinfo('FFmpeg ready', 'ffmpeg and ffprobe were found on PATH.')
            return
        explanation = ffmpeg_help(missing)
        if sys.platform != 'win32':
            messagebox.showerror('FFmpeg missing', explanation)
            return
        if not messagebox.askyesno(
            'Install FFmpeg?',
            explanation + '\n\nRun Windows Package Manager (winget) now? '
            'This installs third-party software and may request Windows approval.'
        ):
            message.set('FFmpeg missing. You can install it manually with winget.')
            return
        run_button.config(state='disabled')
        check_button.config(state='disabled')
        message.set('Installing FFmpeg with winget...')
        future = pool.submit(install_ffmpeg_windows)

        def poll_install() -> None:
            if not future.done():
                root.after(200, poll_install)
                return
            run_button.config(state='normal')
            check_button.config(state='normal')
            try:
                result = future.result()
                message.set(result)
                messagebox.showinfo('FFmpeg installation', result)
            except Exception as exc:
                message.set('FFmpeg installation failed: ' + str(exc))
                messagebox.showerror('FFmpeg installation failed', str(exc))
        root.after(200, poll_install)

    def launch() -> None:
        if not path.get().strip():
            messagebox.showerror('Missing input', 'Select a file or paste a YouTube URL first.')
            return
        if is_youtube_url(path.get()) and missing_ffmpeg():
            # A cache hit needs neither an active YouTube connection nor FFmpeg.
            try:
                reuse = cached_youtube_mp3(path.get()) is not None
            except ValueError:
                reuse = False
            if not reuse:
                offer_ffmpeg_install()
                return
        run_button.config(state='disabled')
        message.set('Working... YouTube download or AI transcription can take several minutes.')
        future = pool.submit(
            convert, path.get(), Path(output.get()), preset.get(), spk4.get(),
            stems.get(), preview.get(), keep_mp3=keep_mp3.get(),
            mp3_only=mp3_only.get(), drum_style=drum_style.get(),
            note_preservation=note_preservation.get(),
            guitar_separation=guitar_separation.get(),
            accompaniment=accompaniment.get(), transcription=transcription.get(),
            voice_selection=voice_selection.get(), max_raw=max_raw.get(),
            arrangement=arrangement.get(),
            core_smoothing=core_smoothing.get())
        def poll() -> None:
            if not future.done():
                root.after(200, poll)
                return
            run_button.config(state='normal')
            try:
                files = future.result()
                message.set(f'Created {len(files)} file(s) in {files[0].parent}')
            except Exception as exc:
                message.set(f'Error: {exc}')
                messagebox.showerror('Conversion failed', str(exc))
        root.after(200, poll)

    run_button = ttk.Button(outer, text='Convert / Download', command=launch)
    run_button.grid(row=17, column=0, columnspan=2, sticky='ew', pady=8, padx=(0, 8))
    check_button = ttk.Button(outer, text='Check / Install FFmpeg', command=offer_ffmpeg_install)
    check_button.grid(row=17, column=2, sticky='ew', pady=8)
    root.protocol('WM_DELETE_WINDOW', lambda: (pool.shutdown(wait=False, cancel_futures=True), root.destroy()))
    root.mainloop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='TandyAMP Studio: YouTube/MP3/MIDI to 16-bit DOS TandyAMP')
    parser.add_argument('input', nargs='?', help='Local MIDI/audio path or quoted single-video YouTube URL')
    parser.add_argument('output_folder', nargs='?', type=Path,
                        help='Parent folder for the generated MIDI and playback files')
    parser.add_argument('-o', '--output', type=Path,
                        help='Set the output folder (default: ./TANDY_OUT)')
    parser.add_argument('--preset', choices=PRESETS,
                        default=DEFAULTS['preset'])
    parser.add_argument('--spk4', choices=['off', 'bass', 'adapt'],
                        default=DEFAULTS['spk4'])
    parser.add_argument('--stems', action='store_true',
                        default=DEFAULTS['stems'],
                        help='Demucs stem separation (audio input)')
    parser.add_argument('--drum-style', choices=['auto', 'rock'],
                        default=DEFAULTS['drum_style'],
                        help='Drum cleanup: auto or rock (requires --stems for audio)')
    parser.add_argument('--note-preservation', choices=['full', 'clean'],
                        default=DEFAULTS['note_preservation'], help='Fuller transcription or legacy cleanup; audio input only')
    parser.add_argument('--guitar-separation', dest='guitar_separation',
                        action='store_true', default=DEFAULTS['guitar_separation'],
                        help='Isolate guitar with Demucs htdemucs_6s; implies stem separation')
    parser.add_argument('--no-guitar-separation', dest='guitar_separation',
                        action='store_false',
                        help='Disable default guitar separation (use --stems for four-stem audio)')
    parser.add_argument('--accompaniment', choices=['off', 'recover', 'harmonize'],
                        default=DEFAULTS['accompaniment'], help='Optional spectral chord recovery / inferred support (requires stems)')
    parser.add_argument('--transcription', choices=['standard', 'sensitive'],
                        default=DEFAULTS['transcription'],
                        help='Sensitive is experimental separated guitar/harmony decoding')
    parser.add_argument('--voice-selection', choices=['legacy', 'smart'],
                        default=DEFAULTS['voice_selection'],
                        help='Smart: protect riff attacks and bass on current DOS builds')
    parser.add_argument('--arrangement', choices=ARRANGEMENTS,
                        help='Tuned (default for audio): pitch correction and phrase voicing; '
                             'Core: sparse phrase score; Musical: fuller; Classic: legacy')
    parser.add_argument('--core-smoothing', choices=['auto', 'on', 'off'],
                        default=DEFAULTS['core_smoothing'],
                        help='Auto connects decoder gaps in Tuned/CORE audio; on also smooths '
                             'imported CORE MIDI; off skips those joins')
    parser.add_argument('--reference-midi', type=Path,
                        help='Optional MIDI guide for Tuned audio conversion')
    parser.add_argument('--reference-channels',
                        help='Guide channels as guitar=1,melody=2,bass=3,drums=10')
    parser.add_argument('--reference-alignment',
                        help='Guide alignment as comma-separated beat=seconds pairs')
    parser.add_argument('--reference-end', type=float,
                        help='End a guided excerpt at this audio time in seconds')
    parser.add_argument('--max-raw', action='store_true',
                        default=DEFAULTS['max_raw'],
                        help='YouTube/audio: six stems, high-recall decoding, no note/velocity/voice pruning; split DOS MIDI by size only')
    parser.add_argument('--preview', dest='preview', action='store_true',
                        default=DEFAULTS['preview'],
                        help='Write an approximate 30-second WAV preview')
    parser.add_argument('--no-preview', dest='preview', action='store_false',
                        help='Skip WAV preview')
    parser.add_argument('--keep-mp3', action='store_true',
                        help='Keep downloaded YouTube source MP3 in generated MIDI folder')
    parser.add_argument('--mp3-only', action='store_true',
                        help='Download YouTube MP3 only, without AI transcription or MIDI')
    parser.add_argument('--mp3-quality', choices=['128', '192', '256', '320'],
                        default=DEFAULTS['mp3_quality'],
                        help='Extracted YouTube MP3 bitrate in kbps (default: 192)')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--cli', '--no-gui', action='store_true', help='Never open the GUI; require input')
    mode.add_argument('--gui', action='store_true', help='Open the graphical interface')
    args = parser.parse_args(argv)
    if args.output_folder is not None and args.output is not None:
        parser.error('specify the output folder once, as a positional argument or with --output')
    output_dir = args.output_folder or args.output
    if args.gui or (args.input is None and not args.cli):
        if output_dir is None:
            gui(args.input or '')
        else:
            gui(args.input or '', initial_output=output_dir)
        return 0
    if args.input is None:
        parser.error('a file or single-video YouTube URL is required in --cli mode')
    if args.max_raw and args.arrangement not in (None, 'classic'):
        print('TandyAMP Studio error: MAX RAW and arranged modes are alternative outputs',
              file=sys.stderr)
        return 1
    arrangement = args.arrangement or _default_arrangement(args.input, args.max_raw)
    reference_options = {
        key: value for key, value in (
            ('reference_midi', args.reference_midi),
            ('reference_channels', args.reference_channels),
            ('reference_alignment', args.reference_alignment),
            ('reference_end', args.reference_end),
        ) if value is not None
    }
    try:
        convert(args.input, output_dir or Path.cwd() / 'TANDY_OUT', args.preset, args.spk4,
                args.stems, args.preview, keep_mp3=args.keep_mp3,
                mp3_only=args.mp3_only, mp3_quality=args.mp3_quality,
                drum_style=args.drum_style,
                note_preservation=args.note_preservation,
                guitar_separation=args.guitar_separation,
                accompaniment=args.accompaniment, transcription=args.transcription,
                voice_selection=args.voice_selection, max_raw=args.max_raw,
                arrangement=arrangement,
                **({'core_smoothing': args.core_smoothing}
                   if args.core_smoothing != DEFAULTS['core_smoothing'] else {}),
                **reference_options)
    except (FileNotFoundError, FileExistsError, ValueError, RuntimeError, OSError, ImportError) as exc:
        print(f'TandyAMP Studio error: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
