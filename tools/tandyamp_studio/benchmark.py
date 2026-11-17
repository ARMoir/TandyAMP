"""Repeatable audio -> stems -> candidates -> Tandy MIDI/WAV comparisons.

Run --help. Private audio and model activations belong in --work-dir, never git.
"""
from __future__ import annotations

import argparse
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sys

from arranger import export, load_midi, prepare
from diagnostics import file_digest, note_metrics, save_stage, write_json


def separated_source(source: Path, work: Path, model: str) -> Path:
    identity = {'source_sha256': file_digest(source), 'model': model,
                'demucs_version': version('demucs'), 'shifts': 0}
    checkpoint = work / 'separation.json'
    root = work / 'stems' / model / source.stem
    names = ['bass', 'vocals', 'other', 'drums']
    if model == 'htdemucs_6s':
        names += ['guitar', 'piano']
    if checkpoint.exists():
        saved = json.loads(checkpoint.read_text(encoding='utf-8'))
        if saved['identity'] != identity:
            raise ValueError('Work directory belongs to another source/model; use a new directory')
        if all((root / (name + '.wav')).is_file() and
               file_digest(root / (name + '.wav')) == saved['stems'].get(name)
               for name in names):
            print('Reusing verified separated stems', flush=True)
            return root
        raise ValueError('Separated stem checkpoint is incomplete or changed; use a new work directory')
    subprocess.run([sys.executable, '-m', 'demucs', '-n', model,
                    '--shifts', '0', '-o', str(work / 'stems'), str(source)], check=True)
    hashes = {name: file_digest(root / (name + '.wav')) for name in names}
    write_json(checkpoint, {'identity': identity, 'stems': hashes})
    return root


def run(source: Path, work: Path, *, stems_dir: Path | None = None,
        reference_midi: Path | None = None, model: str = 'htdemucs_6s',
        profiles=('standard', 'sensitive'), modes=('off', 'recover', 'harmonize'),
        spk4: str = 'adapt', preview_seconds: float = 30.0) -> dict:
    import librosa
    from accompaniment import analyze_accompaniment_audio
    from transcribe import transcribe_stems
    from preview import preview_wav
    source, work = Path(source), Path(work)
    duration = float(librosa.get_duration(path=str(source)))
    work.mkdir(parents=True, exist_ok=True)
    root = Path(stems_dir) if stems_dir else separated_source(source, work, model)
    identity = {'source_sha256': file_digest(source), 'duration': duration,
                'model': model, 'external_stems': stems_dir is not None,
                'stems_sha256': {p.name: file_digest(p) for p in sorted(root.glob('*.wav'))},
                'basic_pitch_version': version('basic-pitch')}
    # Never append a different source/stem set to earlier experiment results.
    manifest = work / 'input.json'
    if manifest.exists() and json.loads(manifest.read_text()) != identity:
        raise ValueError('Benchmark inputs changed; select a new work directory')
    write_json(manifest, identity)
    results = {'input': identity, 'variants': {},
               'interpretation': 'Coverage is not accuracy; audition WAVs and validate on hardware.'}
    if reference_midi:
        results['reference'] = note_metrics(load_midi(reference_midi), duration, spk4)
        results['reference_sha256'] = file_digest(reference_midi)
    for profile in profiles:
        diagnostic_dir = work / profile
        notes = transcribe_stems(root, guitar_separation=model == 'htdemucs_6s',
                                 profile=profile, cache_dir=work / 'predictions',
                                 diagnostics_dir=diagnostic_dir)
        save_stage(diagnostic_dir, 'transcribed', notes, duration, spk4)
        for mode in modes:
            dest = diagnostic_dir / mode
            if any(dest.glob('*.MID')):
                raise FileExistsError(f'Comparison output exists: {dest}; choose new variant/output')
            harmonic = root / ('guitar.wav' if model == 'htdemucs_6s' else 'other.wav')
            support = analyze_accompaniment_audio(harmonic, notes, mode)
            save_stage(dest, 'support', support, duration, spk4)
            candidates = notes + support
            save_stage(dest, 'before-arrangement', candidates, duration, spk4)
            arranged = prepare(candidates, 'balanced', spk4, preserve=True)
            metrics = save_stage(dest, 'arranged', arranged, duration, spk4)
            files = export(arranged, dest)
            flag = {'off': '/NOSPK4', 'bass': '/SPK4', 'adapt': '/SPK4:ADAPT'}[spk4]
            (dest / 'PLAY.BAT').write_bytes(('@ECHO OFF\r\nTANDYAMP ' + flag + '\r\n').encode())
            if preview_seconds > 0:
                preview_wav(arranged, dest / 'PREVIEW.WAV', preview_seconds, spk4)
            metrics['midi_bytes'] = sum(p.stat().st_size for p in files)
            results['variants'][profile + '/' + mode] = metrics
            write_json(work / 'comparison.json', results)
            print(profile, mode, metrics['candidate_seconds'], flush=True)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Local original audio')
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--stems-dir', type=Path, help='Optional existing stems from this exact source')
    parser.add_argument('--reference-midi', type=Path)
    parser.add_argument('--model', choices=['htdemucs', 'htdemucs_6s'], default='htdemucs_6s')
    parser.add_argument('--profiles', nargs='+', choices=['standard', 'sensitive'],
                        default=['standard', 'sensitive'])
    parser.add_argument('--modes', nargs='+', choices=['off', 'recover', 'harmonize'],
                        default=['off', 'recover', 'harmonize'])
    parser.add_argument('--spk4', choices=['off', 'bass', 'adapt'], default='adapt')
    parser.add_argument('--preview-seconds', type=float, default=30.0,
                        help='Use song duration for a full-length preview; 0 disables')
    args = parser.parse_args(argv)
    run(args.source, args.work_dir, stems_dir=args.stems_dir,
        reference_midi=args.reference_midi, model=args.model, profiles=args.profiles,
        modes=args.modes, spk4=args.spk4, preview_seconds=args.preview_seconds)


if __name__ == '__main__':
    main()
