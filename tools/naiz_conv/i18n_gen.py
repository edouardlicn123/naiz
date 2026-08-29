#!/usr/bin/env python3
"""
i18n template generator — extracts translatable text from .nb files.

Usage:
    python -m tools.naiz_conv.i18n_gen <project_dir> [--force]

Scans scene/*.nb, extracts text by command type, generates/merges translation
files in i18n/system_<lang>.txt, role_<lang>.txt, game_<lang>.txt.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from naiz_build.project_config import ProjectConfig
from naiz_lib.nb_line import parse_nb_line as naiz_parse_nb_line


VALID_LANGS = {
    'eng', 'chi', 'cht', 'jpn', 'kor', 'fra', 'deu', 'esp',
    'ptp', 'ptb', 'ita', 'rus', 'pol',
}


def parse_nb_line(line):
    """Parse one NB line, return (cmd_name, args_list, text) or None."""
    parsed = naiz_parse_nb_line(line)
    if parsed is None:
        return None
    return parsed.cmd, parsed.args, parsed.text


def extract_texts(nb_files):
    """Extract translatable texts from .nb files."""
    dialogue_texts = set()
    question_texts = set()
    menu_options = set()

    for nb_path in nb_files:
        with open(nb_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                parsed = naiz_parse_nb_line(line)
                if not parsed:
                    continue

                cmd, args, text, raw = parsed

                if text and cmd not in ('host', 'mainmenu', 'question', 'char', 'bg', 'scene', 'sceneconf'):
                    dialogue_texts.add(text.strip())

                if cmd == 'sceneconf' and text:
                    # sceneconf(){title[,type]}: only the title part (before
                    # the first ',') is translatable; type is a keyword.
                    title_part = text.split(',')[0].strip()
                    if title_part:
                        dialogue_texts.add(title_part)

                if cmd == 'host' and text:
                    dialogue_texts.add(text.strip())

                if cmd == 'question' and raw:
                    # Engine re-splits question args with ';' as top-level
                    # delimiter: argv[0] is the prompt text, each following
                    # segment is "label,var,op,delta" (only label is text).
                    segments = [s.strip() for s in raw.split(';')]
                    if segments and segments[0]:
                        question_texts.add(segments[0])
                    for seg in segments[1:]:
                        label = seg.split(',')[0].strip()
                        if label:
                            question_texts.add(label)

                if cmd == 'mainmenu' and len(args) > 4:
                    for a in args[4:]:
                        a = a.strip()
                        if a:
                            menu_options.add(a)

    return dialogue_texts, question_texts, menu_options


def load_existing_translations(filepath):
    """Load existing translation file, return {key: value} dict and raw lines."""
    entries = {}
    raw_lines = []
    if not filepath.exists():
        return entries, raw_lines

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            raw_line = line.rstrip('\n').rstrip('\r')
            raw_lines.append(raw_line)

            if not raw_line or raw_line.startswith('#'):
                continue

            eq = raw_line.find('=')
            if eq < 0:
                continue

            key = raw_line[:eq].strip()
            val = raw_line[eq + 1:]
            if key:
                entries[key] = val

    return entries, raw_lines


def merge_translations(existing_entries, new_keys):
    """Merge existing translations with new key set."""
    output = []
    seen_keys = set()

    for key, val in existing_entries.items():
        if key in new_keys:
            output.append(f'{key}={val}')
        else:
            output.append(f'# ORPHANED: {key}={val}')
        seen_keys.add(key)

    for key in sorted(new_keys - seen_keys):
        output.append(f'{key}=')

    return output


def load_roles(project_dir):
    """Load character keys from characters.json."""
    json_path = Path(project_dir) / 'characters.json'
    if not json_path.exists():
        print(f'  WARNING: {json_path} not found, skipping role extraction')
        return set()

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        roles = {c['key'] for c in data.get('characters', [])
                 if c.get('key')}
        return roles
    except Exception as e:
        print(f'  WARNING: characters.json read error: {e}')
        return set()


def main():
    if len(sys.argv) < 2:
        print('Usage: python -m tools.naiz_conv.i18n_gen <project_dir> [--force]')
        sys.exit(1)

    proj_dir = Path(sys.argv[1])
    force = '--force' in sys.argv

    if not proj_dir.is_dir():
        print(f'ERROR: {proj_dir} is not a directory')
        sys.exit(1)

    if generate(proj_dir, force) != 0:
        sys.exit(1)
    print('Done.')


def generate(proj_dir, force=False):
    """Generate/refresh i18n translation templates for a project.

    Merges existing translations (preserves values), adds new empty keys for
    newly extracted texts, and marks removed keys as orphaned.  With
    force=True, existing template files are deleted first so keys removed from
    the scripts do not linger as ORPHANED entries.

    @param proj_dir  Project directory (must contain config.toml + scene/)
    @param force     When True, delete existing template files before merging
    @return 0 on success, 1 on error
    """
    if not proj_dir.is_dir():
        print(f'ERROR: {proj_dir} is not a directory')
        return 1

    config_path = proj_dir / 'config.toml'
    if not config_path.exists():
        print(f'ERROR: config.toml not found in {proj_dir}')
        return 1

    try:
        cfg = ProjectConfig(proj_dir)
    except ValueError as e:
        print(f'ERROR: {e}')
        return 1

    source_lang = cfg.get_str('i18n', 'source_lang')
    targets = cfg.get_list('i18n', 'targets') or []

    if not source_lang:
        print('ERROR: i18n.source_lang missing in config.toml')
        return 1
    if not targets:
        print('ERROR: i18n.targets missing or empty in config.toml')
        return 1

    if source_lang in targets:
        print(f'ERROR: source_lang "{source_lang}" is also in i18n.targets (contradiction)')
        return 1

    invalid = [t for t in targets if t not in VALID_LANGS]
    for t in invalid:
        print(f'  WARNING: unknown language code "{t}", skipping')
    targets = [t for t in targets if t in VALID_LANGS]

    scene_dir = proj_dir / 'scene'
    if not scene_dir.is_dir():
        print(f'ERROR: scene/ not found in {proj_dir}')
        return 1

    nb_files = sorted(scene_dir.glob('*.nb'))
    if not nb_files:
        print(f'  WARNING: no .nb files found in {scene_dir}')

    dialogue_texts, question_texts, menu_options = extract_texts(nb_files)
    game_texts = dialogue_texts | question_texts

    roles = load_roles(proj_dir)

    print(f'  Extracted: {len(game_texts)} game texts, {len(menu_options)} menu options, {len(roles)} roles')

    i18n_dir = proj_dir / 'i18n'
    i18n_dir.mkdir(exist_ok=True)

    for lang in targets:
        if force:
            for prefix in ('system', 'role', 'game'):
                fp = i18n_dir / f'{prefix}_{lang}.txt'
                if fp.exists():
                    fp.unlink()

        sys_path = i18n_dir / f'system_{lang}.txt'
        sys_entries, _ = load_existing_translations(sys_path)
        sys_lines = merge_translations(sys_entries, menu_options)
        with open(sys_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sys_lines) + '\n' if sys_lines else '')

        role_path = i18n_dir / f'role_{lang}.txt'
        role_entries, _ = load_existing_translations(role_path)
        role_lines = merge_translations(role_entries, roles)
        with open(role_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(role_lines) + '\n' if role_lines else '')

        game_path = i18n_dir / f'game_{lang}.txt'
        game_entries, _ = load_existing_translations(game_path)
        game_lines = merge_translations(game_entries, game_texts)
        with open(game_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(game_lines) + '\n' if game_lines else '')

        print(f'  {lang}: system={len(sys_lines)} role={len(role_lines)} game={len(game_lines)}')

    return 0


if __name__ == '__main__':
    main()
