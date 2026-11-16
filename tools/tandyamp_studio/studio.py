"""TandyAMP Studio: MP3/WAV/MIDI -> SPK4-aware DOS-compatible MIDI files."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from arranger import PRESETS, export, load_midi, prepare


def convert(input_file: Path, output_dir: Path, preset: str = 'balanced',
            spk4: str = 'bass', stems: bool = False, preview: bool = False) -> list[Path]:
    input_file = Path(input_file).expanduser().resolve()
    if not input_file.is_file():
        raise FileNotFoundError(input_file)
    if input_file.suffix.lower() in ('.mid', '.midi'):
        print(f'Loading MIDI: {input_file}', flush=True)
        notes = load_midi(input_file)
    elif input_file.suffix.lower() in ('.mp3', '.wav', '.flac', '.ogg'):
        from transcribe import transcribe_audio
        print(f'Transcribing audio: {input_file}', flush=True)
        notes = transcribe_audio(input_file, stems=stems)
    else:
        raise ValueError('Input must be MID, MIDI, MP3, WAV, FLAC or OGG')
    print(f'Extracted {len(notes)} note events', flush=True)
    arranged = prepare(notes, preset, spk4 != 'off')
    print(f'Arranged {len(arranged)} events for Tandy PSG + SPK4 {spk4}', flush=True)
    target = Path(output_dir).expanduser().resolve() / (input_file.stem + '_TANDY')
    files = export(arranged, target)
    for f in files:
        print(f'  {f.name} ({f.stat().st_size} bytes)', flush=True)
    playmode = {'off': '/NOSPK4', 'bass': '/SPK4', 'adapt': '/SPK4:ADAPT'}[spk4]
    (target / 'PLAY.BAT').write_bytes(('@ECHO OFF\r\nTANDYAMP ' + playmode + '\r\n').encode('ascii'))
    if preview:
        from preview import preview_wav
        wav = preview_wav(arranged, target / 'PREVIEW.WAV')
        print(f'Approximate 30-second square-wave preview: {wav}', flush=True)
    print(f'Complete. Copy the MID files from {target} to your DOS CF card.', flush=True)
    return files


def gui() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from concurrent.futures import ThreadPoolExecutor
    try:
        from tkinterdnd2 import TkinterDnD, DND_FILES
        root = TkinterDnD.Tk()
    except ImportError:
        root = tk.Tk()
        DND_FILES = None
    root.title('TandyAMP Studio - MP3 / MIDI to Tandy DOS')
    root.geometry('670x350')
    root.minsize(600, 320)
    path = tk.StringVar()
    output = tk.StringVar(value=str(Path.home() / 'Music'))
    preset = tk.StringVar(value='balanced')
    spk4 = tk.StringVar(value='bass')
    stems = tk.BooleanVar(value=False)
    preview = tk.BooleanVar(value=True)
    message = tk.StringVar(value='Select an MP3, WAV or MIDI file to begin.')
    outer = ttk.Frame(root, padding=16)
    outer.pack(fill='both', expand=True)
    outer.columnconfigure(1, weight=1)
    ttk.Label(outer, text='Source file').grid(row=0, column=0, sticky='w', pady=7)
    ttk.Entry(outer, textvariable=path).grid(row=0, column=1, sticky='ew', padx=8)
    ttk.Button(outer, text='Browse...', command=lambda: path.set(filedialog.askopenfilename(filetypes=[('Music', '*.mid *.midi *.mp3 *.wav *.flac *.ogg'), ('All files', '*.*')]))).grid(row=0, column=2)
    ttk.Label(outer, text='Output folder').grid(row=1, column=0, sticky='w', pady=7)
    ttk.Entry(outer, textvariable=output).grid(row=1, column=1, sticky='ew', padx=8)
    ttk.Button(outer, text='Browse...', command=lambda: output.set(filedialog.askdirectory() or output.get())).grid(row=1, column=2)
    ttk.Label(outer, text='Preset').grid(row=2, column=0, sticky='w', pady=7)
    ttk.Combobox(outer, textvariable=preset, values=list(PRESETS), state='readonly', width=19).grid(row=2, column=1, sticky='w', padx=8)
    ttk.Label(outer, text='SPK4').grid(row=3, column=0, sticky='w', pady=7)
    ttk.Combobox(outer, textvariable=spk4, values=['off', 'bass', 'adapt'], state='readonly', width=19).grid(row=3, column=1, sticky='w', padx=8)
    ttk.Checkbutton(outer, text='Separate MP3/WAV stems (Demucs; improves results, slower)', variable=stems).grid(row=4, column=0, columnspan=3, sticky='w', pady=3)
    ttk.Checkbutton(outer, text='Generate 30-second approximate WAV preview', variable=preview).grid(row=5, column=0, columnspan=3, sticky='w', pady=3)
    status = ttk.Label(outer, textvariable=message, wraplength=620)
    status.grid(row=7, column=0, columnspan=3, sticky='w', pady=13)
    if DND_FILES:
        status.configure(text='')
        root.drop_target_register(DND_FILES)
        root.dnd_bind('<<Drop>>', lambda event: path.set(root.tk.splitlist(event.data)[0]))
    pool = ThreadPoolExecutor(max_workers=1)

    def launch() -> None:
        if not path.get().strip():
            messagebox.showerror('Missing input', 'Select a music file first.')
            return
        run_button.config(state='disabled')
        message.set('Working... Transcription may take several minutes on a laptop.')
        future = pool.submit(convert, Path(path.get()), Path(output.get()), preset.get(), spk4.get(), stems.get(), preview.get())
        def poll() -> None:
            if not future.done():
                root.after(200, poll)
                return
            run_button.config(state='normal')
            try:
                files = future.result()
                message.set(f'Created {len(files)} DOS MIDI file(s) in {files[0].parent}')
            except Exception as exc:
                message.set(f'Error: {exc}')
                messagebox.showerror('Conversion failed', str(exc))
        root.after(200, poll)

    run_button = ttk.Button(outer, text='Convert for TandyAMP', command=launch)
    run_button.grid(row=6, column=0, columnspan=3, sticky='ew', pady=12)
    root.protocol('WM_DELETE_WINDOW', lambda: (pool.shutdown(wait=False, cancel_futures=True), root.destroy()))
    root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(description='TandyAMP Studio: laptop audio/MIDI arranger for 7MHz Tandy 1000 EX')
    parser.add_argument('input', nargs='?', type=Path, help='MIDI or audio file; omit to open GUI')
    parser.add_argument('-o', '--output', type=Path, default=Path.cwd() / 'TANDY_OUT')
    parser.add_argument('--preset', choices=PRESETS, default='balanced')
    parser.add_argument('--spk4', choices=['off', 'bass', 'adapt'], default='bass')
    parser.add_argument('--stems', action='store_true', help='Demucs stem separation for audio input')
    parser.add_argument('--preview', action='store_true', help='Create approximate WAV preview')
    parser.add_argument('--gui', action='store_true', help='Force graphical launcher')
    args = parser.parse_args()
    if args.gui or args.input is None:
        gui()
        return 0
    try:
        convert(args.input, args.output, args.preset, args.spk4, args.stems, args.preview)
    except (FileNotFoundError, FileExistsError, ValueError, RuntimeError, OSError, ImportError) as exc:
        print(f'TandyAMP Studio error: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
