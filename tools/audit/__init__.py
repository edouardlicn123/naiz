"""tools.audit -- scripted anti-regression bug audit.

Turns the AGENTS.md section-17 rule set (C1-C20, P1-P13, S1-S9) into
executable, per-file checks with git-aware incremental state.  Every rule
is classified as:

  AUTO    -- deterministic pattern match, expected zero false positives
  HEUR    -- static heuristic, emits candidates for human confirmation
  MANUAL  -- semantics that cannot be scripted; emits a targeted review
             checklist so the AI only re-reads specific files/lines

Run:
    python -m tools.audit.audit            # incremental audit (git state aware)
    python -m tools.audit.audit --reset    # force a full re-check

`start.sh fullaudit` orchestrates this plus pytest/py_compile/bash-n/
symbol_audit/make and writes logs/fullaudit_<ts>.log.
"""