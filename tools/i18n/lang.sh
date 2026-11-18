#!/bin/bash
# Naiz dev-tools i18n library.
#
# Default language: English.  The English string itself is the lookup key,
# so missing translations fall back to the English original (never blank).
#
# Language preference is stored in $ROOT/.naiz_lang (single token:
# eng | chi | jpn | kor).  The NAIZ_LANG env var overrides the file.
#
# Usage from any script:
#   ROOT="$(cd "$(dirname "$0")" && pwd)"
#   source "$ROOT/tools/i18n/lang.sh"
#   echo "$(_t "Environment check")"
#
# Change language:
#   _naiz_set_lang chi   # writes $ROOT/.naiz_lang

# Resolve the language preference file.  Callers must set ROOT before sourcing.
_naiz_lang_file() {
    if [ -n "${ROOT:-}" ]; then
        printf '%s\n' "$ROOT/.naiz_lang"
    else
        printf '%s\n' ".naiz_lang"
    fi
}

# Print the current language code (eng|chi|jpn|kor), defaulting to eng.
_naiz_current_lang() {
    local lang="${NAIZ_LANG:-}"
    if [ -z "$lang" ]; then
        local f
        f="$(_naiz_lang_file)"
        if [ -f "$f" ]; then
            lang="$(tr -d '[:space:]' < "$f")"
        fi
    fi
    case "$lang" in
        eng|chi|jpn|kor) printf '%s\n' "$lang" ;;
        *) printf '%s\n' "eng" ;;
    esac
}

# Persist the language choice to $ROOT/.naiz_lang.
_naiz_set_lang() {
    local lang="$1"
    case "$lang" in
        eng|chi|jpn|kor) ;;
        *) echo "[i18n] invalid language: $lang" >&2; return 1 ;;
    esac
    printf '%s\n' "$lang" > "$(_naiz_lang_file)"
}

# Load the translation table for the current language into the global
# associative array _NAIZ_T.  English needs no table (identity).
_naiz_load_table() {
    declare -gA _NAIZ_T=()
    local lang
    lang="$(_naiz_current_lang)"
    if [ "$lang" = "eng" ]; then
        return 0
    fi
    local table
    table="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/strings_${lang}.sh"
    if [ -f "$table" ]; then
        # shellcheck disable=SC1090
        source "$table"
    fi
}

# Translate a string.  Usage: _t "English text"
# Falls back to the English original when no translation is registered.
# The table is loaded once at source time; changing language mid-session
# (via lang_menu) takes effect on the next script invocation.
_t() {
    local key="$1"
    printf '%s' "${_NAIZ_T[$key]:-$key}"
}

# Initialise the table when this library is sourced.
_naiz_load_table
