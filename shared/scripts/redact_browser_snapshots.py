#!/usr/bin/env python3
"""Redact credential-shaped strings from browser-automation snapshots on disk.

Why this exists
---------------
Browser automation returns an accessibility tree. When a page has a password
field that the browser's password manager has autofilled, the value is in that
tree, and the tree gets written to disk as a snapshot file. On 2026-08-12 an AWS
console sign-in page put a console password into a snapshot, and an earlier
snapshot captured a Databricks personal access token the same way.

Masking after the fact is the weaker half of the fix. The stronger half is not
snapshotting a page that has a password field at all -- fill it without reading
it back. See the browser-automation rule in AGENTS.md. This script exists for
the cases where that rule was not followed, so the value does not persist.

Idempotent: running it twice changes nothing the second time.

Usage
-----
    redact_browser_snapshots.py                # scan the default directories
    redact_browser_snapshots.py DIR [DIR ...]  # scan specific directories
    redact_browser_snapshots.py --check        # report only, exit 1 if hits

Exit codes
----------
    0  nothing found, or found and redacted
    1  --check was passed and unredacted credentials are present
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Directories browser-automation tooling writes snapshots into. Both the
# workspace-local and the temp-dir location are checked, because which one is
# used depends on the tool's working directory.
DEFAULT_DIRS = [
    Path(".playwright-mcp"),
    Path("/tmp/.playwright-mcp"),
    Path(os.environ.get("TMPDIR", "/tmp")) / ".playwright-mcp",
]

PLACEHOLDER = "<REDACTED-BY-redact_browser_snapshots>"

# Each pattern must match the secret itself, not the surrounding context, so
# that re.sub replaces only the value. Keep these anchored enough to avoid
# eating ordinary prose.
# **境界に ``\b`` を使わない。** Python の ``\b`` は Unicode 対応なので、``ン`` や ``は`` の
# ような日本語の文字は語構成文字として扱われる。その結果 ``アクセストークンdapi…`` の
# ``dapi`` の直前は「語の途中」と判定され、``\b`` は一致しない。**日本語 UI のブラウザから
# 取った accessibility tree は、まさにこの形になる。** このスクリプトが存在する理由である
# 2026-08-12 の事故は日本語表示の AWS コンソールで起きており、``\b`` 版はその入力に対して
# 3 パターンが無言だった（``--selftest`` の JP-adjacent ケースが両方向を押さえている）。
#
# ASCII のみの前後guard に置き換える。同じ ``\b`` が Go/RE2（gitleaks）では ASCII 限定で
# 安全に働くので、**エンジンごとに意味が違う。** 移植するときは engine を確認すること。
_LEAD = r"(?<![A-Za-z0-9])"
_TRAIL = r"(?![A-Za-z0-9])"

PATTERNS: dict[str, re.Pattern[str]] = {
    # Databricks personal access token
    "databricks-pat": re.compile(_LEAD + r"dapi[0-9a-f]{28,}" + _TRAIL),
    # AWS access key IDs. The temporary (ASIA) form is the one that shows up in
    # assume-role output; the long-term (AKIA) form should never be here at all.
    "aws-access-key-id": re.compile(_LEAD + r"(?:ASIA|AKIA)[0-9A-Z]{16}" + _TRAIL),
    # AWS STS session tokens start with a recognisable prefix and are long.
    "aws-session-token": re.compile(_LEAD + r"IQoJ[A-Za-z0-9/+=]{60,}"),
    # A password field whose value survived into the tree. The value is the
    # trailing group; the label is kept so the redaction is auditable.
    "password-field-value": re.compile(
        r'(?P<label>textbox\s+"(?:[^"]*(?:パスワード|[Pp]assword)[^"]*)"[^\n:]*:\s*)'
        r"(?P<value>\S[^\n]*)"
    ),
    # Bearer tokens and Authorization headers captured from network panels.
    # This one survived the \b bug by accident: with Japanese before
    # "authorization:", the alternation still matched the later bare "bearer",
    # which is space-preceded. Made deliberate rather than left to luck.
    "bearer-token": re.compile(
        r"(?i)" + _LEAD + r"(?:bearer|authorization:\s*bearer)\s+[A-Za-z0-9._\-]{20,}"
    ),
}


def redact_text(text: str) -> tuple[str, dict[str, int]]:
    """Return the redacted text and a per-pattern hit count."""
    counts: dict[str, int] = {}
    for name, rx in PATTERNS.items():
        if name == "password-field-value":
            # Count only real changes. Returning the match unchanged still
            # counts as a substitution for subn(), which would make the script
            # report the same file forever.
            changed = 0

            def _sub(m: re.Match[str]) -> str:
                nonlocal changed
                if PLACEHOLDER in m.group("value"):
                    return m.group(0)
                changed += 1
                return m.group("label") + PLACEHOLDER

            text = rx.sub(_sub, text)
            n = changed
        else:
            text, n = rx.subn(PLACEHOLDER, text)
        if n:
            counts[name] = n
    return text, counts


def scan(dirs: list[Path], check_only: bool) -> int:
    total = 0
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if not f.is_file():
                continue
            try:
                original = f.read_text(errors="ignore")
            except OSError:
                continue
            redacted, counts = redact_text(original)
            if not counts:
                continue
            summary = ", ".join(f"{k} x{v}" for k, v in sorted(counts.items()))
            total += sum(counts.values())
            if check_only:
                print(f"UNREDACTED {f}: {summary}", file=sys.stderr)
            else:
                f.write_text(redacted)
                # Snapshots are transient artefacts; tighten permissions anyway
                # so a leftover file is not world-readable.
                try:
                    f.chmod(0o600)
                except OSError:
                    pass
                print(f"redacted {f}: {summary}", file=sys.stderr)
    if check_only and total:
        return 1
    return 0


# 各ケースは「ASCII 形」と「日本語隣接形」を対にしてある。**日本語形だけを試すと、英語側の
# 検出を壊す修正が通る。** 逆に ASCII 形だけを試すと、この検査が実際に落ちた穴（Unicode の
# ``\b``）を再導入しても気づけない。両方を要求することが、片端だけ直して記録だけ残す状態を防ぐ。
_PAT = "dapi" + "0" * 32
_KEY = "ASIA" + "B" * 16
_TOK = "IQoJ" + "c" * 70

SELFTEST_CASES: list[tuple[str, str, bool]] = [
    # (ラベル, 入力, 伏せられるべきか)
    ("pat ascii", f"token: {_PAT} end", True),
    ("pat jp-lead", f"アクセストークン{_PAT} を保存", True),
    ("pat jp-both", f"トークンは{_PAT}です", True),
    ("key ascii", f"AccessKeyId: {_KEY}.", True),
    ("key jp-lead", f"アクセスキーは{_KEY}です", True),
    ("tok ascii", f"SessionToken: {_TOK}", True),
    ("tok jp-lead", f"セッショントークンは{_TOK}", True),
    ("bearer ascii", "authorization: bearer " + "a" * 26, True),
    ("bearer jp-lead", "ヘッダーはauthorization: bearer " + "a" * 26, True),
    ("password field jp label", 'textbox "パスワード" focused: Hunter2Hunter2', True),
    ("password field en label", 'textbox "Password" focused: Hunter2Hunter2', True),
    # 否定側。境界を丸ごと外すとここが落ちる。
    ("pat embedded in longer token", f"x{_PAT}", False),
    ("key embedded in longer token", f"NOTASIA{'B' * 16}", False),
    ("ordinary prose untouched", "dapi is a prefix, 42 GB is a size", False),
    ("bearer too short", "authorization: bearer abc", False),
]


def selftest() -> int:
    bad = []
    for label, text, want in SELFTEST_CASES:
        out, counts = redact_text(text)
        got = out != text
        if got != want:
            bad.append((label, want, got, counts))
    for label, want, got, counts in bad:
        print(
            f"selftest FAIL {label}: expected redacted={want} got={got} {counts}",
            file=sys.stderr,
        )
    if bad:
        return 1
    print(f"selftest: {len(SELFTEST_CASES)} case(s) passed")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    check_only = "--check" in argv
    args = [a for a in argv if not a.startswith("--")]
    dirs = [Path(a) for a in args] if args else DEFAULT_DIRS
    return scan(dirs, check_only)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
