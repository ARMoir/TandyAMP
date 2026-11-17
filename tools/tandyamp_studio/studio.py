"""TandyAMP Studio: local MIDI/audio or YouTube -> SPK4-aware DOS MIDI."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import tempfile

from arranger import PRESETS, export, load_midi, prepare, voice_coverage
from dependencies import ffmpeg_help, install_ffmpeg_windows, missing_ffmpeg
from youtube import cached_youtube_mp3, download_youtube_mp3, is_youtube_url, safe_name


def _convert_local(input_file: Path, output_dir: Path, target_name: str,
                   preset: str, spk4: str, stems: bool, preview: bool,
                   saved_mp3: Path | None = None,
                   drum_style: str = 'auto',
                   note_preservation: str = 'full',
                   guitar_separation: bool = False,
                   accompaniment: str = 'off') -> list[Path]:
    audio_input = input_file.suffix.lower() in ('.mp3', '.wav', '.flac', '.ogg')
    if input_file.suffix.lower() in ('.mid', '.midi'):
        print(f'Loading MIDI: {input_file}', flush=True)
        notes = load_midi(input_file)
    elif input_file.suffix.lower() in ('.mp3', '.wav', '.flac', '.ogg'):
        from transcribe import transcribe_audio
        print(f'Transcribing audio: {input_file}', flush=True)
        notes = transcribe_audio(input_file, stems=stems,
                                 drum_style=drum_style,
                                 preservation=note_preservation,
                                 guitar_separation=guitar_separation,
                                 accompaniment=accompaniment)
    else:
        raise ValueError('Input must be MID, MIDI, MP3, WAV, FLAC, OGG, or a YouTube video URL')
    print(f'Extracted {len(notes)} note events', flush=True)
    arranged = prepare(notes, preset, spk4,
                       preserve=(audio_input and note_preservation == 'full'))
    if audio_input and note_preservation == 'full':
        print('Full mode preserves up to six MIDI candidates at once; '
              'TandyAMP still plays at most three PSG tones plus '
              'an eligible SPK4 bass.', flush=True)
    print(f'Arranged {len(arranged)} events for Tandy PSG + SPK4 {spk4}', flush=True)
    inferred = [n for n in arranged if n.part == 'accomp']
    if audio_input:
        print('  Original/AI pitched notes: {}; inferred accompaniment: {}'.format(
            sum(n.part not in ('drums', 'accomp') for n in arranged),
            len(inferred)), flush=True)
    for title, sample in (('Input after transcription', notes),
                          ('Hardware-limited output', arranged)):
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
    target = output_dir / (target_name + '_TANDY')
    if saved_mp3 is not None and (target / 'SOURCE.MP3').exists():
        raise FileExistsError(f'Refusing to overwrite existing SOURCE.MP3 in {target}')
    files = export(arranged, target)
    if audio_input and accompaniment != 'off':
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
        wav = preview_wav(arranged, target / 'PREVIEW.WAV', spk4=spk4)
        print(f'Approximate 30-second square-wave preview: {wav}', flush=True)
    if saved_mp3 is not None:
        shutil.copyfile(saved_mp3, target / 'SOURCE.MP3')
        print(f'Kept original MP3: {target / "SOURCE.MP3"}', flush=True)
    print(f'Complete. Copy MID files and PLAY.BAT from {target} to your DOS CF card.', flush=True)
    return files


def convert(input_file: str | Path, output_dir: Path, preset: str = 'balanced',
            spk4: str = 'bass', stems: bool = False, preview: bool = False,
            *, keep_mp3: bool = False, mp3_only: bool = False,
            mp3_quality: str = '192', drum_style: str = 'auto',
            note_preservation: str = 'full',
            guitar_separation: bool = False,
            accompaniment: str = 'off') -> list[Path]:
    """Noninteractive pipeline; a validated YouTube MP3 is reused from
    the persistent OS temp cache whenever possible. Outputs are unchanged.
    """
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
    source = str(input_file).strip()
    if not source:
        raise ValueError('Provide a music file or YouTube video URL')
    output_dir = Path(output_dir).expanduser().resolve()
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
                                  drum_style=drum_style,
                                  note_preservation=note_preservation,
                                  guitar_separation=guitar_separation,
                                  accompaniment=accompaniment)
    if source.lower().startswith(('http://', 'https://')):
        raise ValueError('Only single-video YouTube links are supported (https://youtu.be/... or youtube.com/watch?v=...)')
    if keep_mp3 or mp3_only:
        raise ValueError('--keep-mp3 and --mp3-only apply to YouTube URLs only')
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return _convert_local(path, output_dir, path.stem, preset, spk4, stems,
                          preview, drum_style=drum_style,
                          note_preservation=note_preservation,
                          guitar_separation=guitar_separation,
                          accompaniment=accompaniment)


def gui(initial_input: str = '') -> None:
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
    root.geometry('710x550')
    root.minsize(625, 505)
    path = tk.StringVar(value=initial_input)
    output = tk.StringVar(value=str(Path.home() / 'Music'))
    preset = tk.StringVar(value='balanced')
    spk4 = tk.StringVar(value='bass')
    drum_style = tk.StringVar(value='auto')
    note_preservation = tk.StringVar(value='full')
    guitar_separation = tk.BooleanVar(value=False)
    accompaniment = tk.StringVar(value='off')
    stems = tk.BooleanVar(value=False)
    preview = tk.BooleanVar(value=True)
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
    ttk.Checkbutton(outer, text='Generate approximate WAV preview', variable=preview).grid(row=9, column=0, columnspan=3, sticky='w', pady=2)
    ttk.Checkbutton(outer, text='Keep downloaded YouTube MP3 alongside MIDI', variable=keep_mp3).grid(row=10, column=0, columnspan=3, sticky='w', pady=2)
    ttk.Checkbutton(outer, text='MP3 only: download audio, skip MIDI transcription', variable=mp3_only).grid(row=11, column=0, columnspan=3, sticky='w', pady=2)
    status = ttk.Label(outer, textvariable=message, wraplength=660)
    status.grid(row=13, column=0, columnspan=3, sticky='w', pady=8)
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
            accompaniment=accompaniment.get())
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
    run_button.grid(row=12, column=0, columnspan=2, sticky='ew', pady=8, padx=(0, 8))
    check_button = ttk.Button(outer, text='Check / Install FFmpeg', command=offer_ffmpeg_install)
    check_button.grid(row=12, column=2, sticky='ew', pady=8)
    root.protocol('WM_DELETE_WINDOW', lambda: (pool.shutdown(wait=False, cancel_futures=True), root.destroy()))
    root.mainloop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='TandyAMP Studio: YouTube/MP3/MIDI to 16-bit DOS TandyAMP')
    parser.add_argument('input', nargs='?', help='Local MIDI/audio path or quoted single-video YouTube URL')
    parser.add_argument('-o', '--output', type=Path, default=Path.cwd() / 'TANDY_OUT',
                        help='Parent directory for generated files')
    parser.add_argument('--preset', choices=PRESETS, default='balanced')
    parser.add_argument('--spk4', choices=['off', 'bass', 'adapt'], default='bass')
    parser.add_argument('--stems', action='store_true', help='Demucs stem separation (audio input)')
    parser.add_argument('--drum-style', choices=['auto', 'rock'], default='auto',
                        help='Drum cleanup: auto or rock (requires --stems for audio)')
    parser.add_argument('--note-preservation', choices=['full', 'clean'],
                        default='full', help='Fuller transcription or legacy cleanup; audio input only')
    parser.add_argument('--guitar-separation', action='store_true',
                        help='Isolate guitar with Demucs htdemucs_6s; implies --stems')
    parser.add_argument('--accompaniment', choices=['off', 'recover', 'harmonize'],
                        default='off', help='Optional spectral chord recovery / inferred support (requires stems)')
    parser.add_argument('--preview', action='store_true', help='Approximate 30-second WAV preview')
    parser.add_argument('--keep-mp3', action='store_true',
                        help='Keep downloaded YouTube source MP3 in generated MIDI folder')
    parser.add_argument('--mp3-only', action='store_true',
                        help='Download YouTube MP3 only, without AI transcription or MIDI')
    parser.add_argument('--mp3-quality', choices=['128', '192', '256', '320'], default='192',
                        help='Extracted YouTube MP3 bitrate in kbps (default: 192)')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--cli', '--no-gui', action='store_true', help='Never open the GUI; require input')
    mode.add_argument('--gui', action='store_true', help='Open the graphical interface')
    args = parser.parse_args(argv)
    if args.gui or (args.input is None and not args.cli):
        gui(args.input or '')
        return 0
    if args.input is None:
        parser.error('a file or single-video YouTube URL is required in --cli mode')
    try:
        convert(args.input, args.output, args.preset, args.spk4,
                args.stems, args.preview, keep_mp3=args.keep_mp3,
                mp3_only=args.mp3_only, mp3_quality=args.mp3_quality,
                drum_style=args.drum_style,
                note_preservation=args.note_preservation,
                guitar_separation=args.guitar_separation,
                accompaniment=args.accompaniment)
    except (FileNotFoundError, FileExistsError, ValueError, RuntimeError, OSError, ImportError) as exc:
        print(f'TandyAMP Studio error: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
