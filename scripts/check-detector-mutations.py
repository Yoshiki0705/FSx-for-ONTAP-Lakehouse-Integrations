#!/usr/bin/env python3
"""検出器の selftest が、壊し方を識別できることを確認する（mutation テスト）。

**selftest が通ることと、selftest が守っていることは別。** ある検出器の境界を
``(?![A-Za-z0-9])`` から ``\\b`` に戻すと、日本語隣接の入力で無言になる。その退行を
selftest が捕まえるかどうかは、**selftest を読んでも分からない。壊して走らせて初めて
分かる。**

さらに区別が要る。**「検出できること」と「識別できること」は別。** ``\\b`` に戻す変異で
selftest が落ちるのを見ても、それは「正しい境界」と「境界なし」を区別した証拠にはならない。
guard を空にする変異は一致範囲を広げるだけなので、**肯定側のケースだけを持つ selftest は
原理的にそれを検出できない。** 否定ケース（正当な文字列の部分文字列）が要る。

だから各変異は「この selftest は落ちなければならない」という主張であり、
**落ちなかった変異は、その guard がテストに守られていないことの証拠**として報告する。

手で 2 通り回した確認は次回に残らない。ここに書けば残る。

使い方:
  python3 scripts/check-detector-mutations.py            # 全変異
  python3 scripts/check-detector-mutations.py --list     # 一覧のみ
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (対象, ラベル, 置換前, 置換後, この変異が表す実際の不具合)
#
# 置換前の文字列は対象ファイルに実在しなければならない。**実在しない置換は「変異なし」の
# ままテストを走らせ、落ちないので「守られていない」と誤報告する** ので、下で存在を検査する。
MUTATIONS: list[tuple[str, str, str, str, str]] = [
    (
        "scripts/check-doc-number-parity.py",
        "trailing guard -> Unicode \\b",
        r'r"(?![A-Za-z0-9_])"',
        r'r"\b"',
        "CJK が直後に続く 100MB以上 を読めなくなる（元の不具合そのもの）",
    ),
    (
        "scripts/check-doc-number-parity.py",
        "leading guard -> Unicode \\b",
        r'r"(?<![A-Za-z0-9_.])(\d[\d,]*(?:\.\d+)?)\s*"',
        r'r"\b(\d[\d,]*(?:\.\d+)?)\s*"',
        "CJK が直前にある 約100MB を読めなくなる（もう一端）",
    ),
    (
        "scripts/check-doc-number-parity.py",
        "leading guard removed (not replaced)",
        r'r"(?<![A-Za-z0-9_.])(\d[\d,]*(?:\.\d+)?)\s*"',
        r'r"(\d[\d,]*(?:\.\d+)?)\s*"',
        ".5 GB/s を 5 GB/s と読む — 10 倍の読み違い。一致範囲が広がるだけなので、"
        "肯定ケースでは原理的に検出できない。この変異は初回実行で生き残った",
    ),
    (
        "scripts/check-doc-number-parity.py",
        "trailing guard removed (not replaced)",
        r'r"(?![A-Za-z0-9_])"',
        r'r""',
        "100MBps の MB を容量として拾う。同じく肯定ケースでは検出できない",
    ),
    (
        "shared/scripts/redact_browser_snapshots.py",
        "credential leading guard -> Unicode \\b",
        '_LEAD = r"(?<![A-Za-z0-9])"',
        '_LEAD = r"\\b"',
        "アクセストークンdapi… を伏せられなくなる。"
        "gitleaks は素の AWS アクセスキー ID を拾わないので、ここが唯一の層",
    ),
    (
        "shared/scripts/redact_browser_snapshots.py",
        "credential trailing guard -> Unicode \\b",
        '_TRAIL = r"(?![A-Za-z0-9])"',
        '_TRAIL = r"\\b"',
        "トークンは…です の形を伏せられなくなる",
    ),
    (
        "shared/scripts/redact_browser_snapshots.py",
        "credential guards removed",
        '_LEAD = r"(?<![A-Za-z0-9])"',
        '_LEAD = r""',
        "長いトークンの一部を伏せる誤検出。否定ケースだけが止める",
    ),
    (
        "scripts/check-doc-number-parity.py",
        "compare occurrence counts instead of presence",
        "    only_en = sorted((k, qe[k]) for k in qe.keys() - qj.keys())",
        "    only_en = sorted(\n"
        "        (k, qe[k]) for k in qe if len(qe[k]) != len(qj.get(k, []))\n"
        "    )",
        "同じ数量を EN が 3 回・JA が 2 回書くだけで報告する。言い換えの差で"
        "埋め尽くされ、直せない警告になる。ソースが「本数の差は報告しない」と"
        "書いている禁止に対応する変異",
    ),
    (
        "scripts/check-doc-number-parity.py",
        "stale baseline entry treated as clean",
        'return "stale" if known else "clean"',
        'return "clean"',
        "KNOWN_DIVERGENT_PAIRS が縮むしかない性質を失う。直った対のエントリが残り、"
        "その対は以後どんな食い違いでも報告されなくなる。**実行結果は静かに正常に見える**",
    ),
    (
        "scripts/check-doc-number-parity.py",
        "allow marker: look for inert only, not harmful",
        "    return not (\n"
        "        _diff_count(en_text, ja_text, False) > _diff_count(en_text, ja_text, True)\n"
        "    )",
        "    return _diff_count(en_text, ja_text, False) == _diff_count(\n"
        "        en_text, ja_text, True\n"
        "    )",
        "共有している数量に付いたマーカー（存在しない食い違いを作る側）を見逃す。"
        "不活性だけを探す最初の実装そのもの",
    ),
    (
        "scripts/check-doc-number-parity.py",
        "code-span mention counted as a real marker",
        "    return CODE_SPAN.sub(\"\", line)",
        "    return line",
        "マーカーを説明した行がマーカーとして計上される。うるさい側（説明を書くと落ちる）と"
        "静かな側（説明行の数量が抑制される）の両方",
    ),
    (
        "scripts/check-heading-style.py",
        "code-span mention counted as a real marker",
        "    return CODE_SPAN.sub(\"\", line)",
        "    return line",
        "構文例を含む見出しがマーカー付きと誤認され、その見出しの違反が免除される。"
        "**説明している行が自分を検査対象から外す**",
    ),
    (
        "scripts/check-heading-style.py",
        "inert check re-implements the predicate instead of calling is_violation",
        "        if not is_violation(m.group(2).strip()):\n"
        "            found.append((n, m.group(2).strip()))",
        "        h = m.group(2).strip()\n"
        "        if not JAPANESE.search(h) or not VERBAL.search(h):\n"
        "            found.append((n, h))",
        "監査本体と不活性検査で判定の幅がずれる。マーカー付きの見出しが「必要」かつ"
        "「不活性」になり、**消しても残しても落ちる**行ができる",
    ),
    (
        "scripts/check-heading-style.py",
        "allow marker inertness never reported",
        "        if not is_violation(m.group(2).strip()):\n"
        "            found.append((n, m.group(2).strip()))",
        "        if False:\n            found.append((n, m.group(2).strip()))",
        "見出しを直したあとに残った許可マーカーが永久に残る。"
        "抑制が縮むしかない性質を失う",
    ),
    (
        "scripts/check-heading-style.py",
        "inert check drops its fence guard",
        "        if in_fence or not ALLOW.search(effective(line)):",
        "        if not ALLOW.search(effective(line)):",
        "フェンス内の構文例が不活性マーカーとして報告される。**この変異は、表が 1 行の"
        "文字列ばかりだった間、全テストを通過していた**（複数行の入力が無かった）",
    ),
    (
        "scripts/check-heading-style.py",
        "is_violation stops stripping the marker",
        '    h = ALLOW.sub("", effective(heading_text)).strip()',
        "    h = effective(heading_text).strip()",
        "見出し本文の末尾がマーカーになり述語判定が外れる。**除去を 2 か所に書いていた間、"
        "この変異は無害化されて全テストを通過していた** — 冗長な防御はテストの感度を下げる",
    ),
    (
        "scripts/check-heading-style.py",
        "drop ない from the predicate class",
        "|のか|か|ない",
        "|のか|か",
        "『…できない』のような否定の述語見出しを無言で通す",
    ),
    (
        "scripts/check-heading-style.py",
        "add れ to the う段 class",
        "[うくぐすずつぬふぶむる]",
        "[うくぐすずつぬふぶむるれ]",
        "連用形の名詞化（崩れ / 遅れ）を誤検出する。許可リストでは直せない",
    ),
]


def run_selftest(source_path: Path, source_text: str) -> bool:
    """変異させたソースで --selftest を走らせ、通ったか (True) を返す。

    subprocess で走らせる。**selftest は ROOT を触らない**（CASES だけを見る）ので、
    一時ディレクトリに置いても結果は変わらない。exec で読み込むより、CI が実際に
    呼ぶ経路に近い。
    """
    with tempfile.TemporaryDirectory() as td:
        mutant = Path(td) / source_path.name
        mutant.write_text(source_text, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(mutant), "--selftest"],
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0


def main() -> int:
    if "--list" in sys.argv:
        for target, label, _, _, why in MUTATIONS:
            print(f"{target}\n  {label}\n    -> {why}")
        return 0

    targets = sorted({m[0] for m in MUTATIONS})

    # 対照。変異前が通らないなら、以降の「落ちた」は変異のせいだと言えない。
    print("control: unmutated selftests must pass")
    for t in targets:
        p = ROOT / t
        if not run_selftest(p, p.read_text(encoding="utf-8")):
            print(f"  FAIL {t}: selftest does not pass unmutated", file=sys.stderr)
            return 1
        print(f"  ok   {t}")

    print("\nmutations: each must make its selftest fail")
    survived = []
    missing = []
    for target, label, old, new, why in MUTATIONS:
        p = ROOT / target
        text = p.read_text(encoding="utf-8")
        # **出現回数を 1 に固定する。** 0 回なら変異なしで走って何も証明しない。2 回以上だと
        # ``replace(..., 1)`` は片方しか壊さないので、**部分的に壊れた検出器で selftest が
        # 落ち、guard 全体が守られていると誤読する。** 弱い変異が「殺された」と出るのは、
        # 生き残るより危険な向きの誤りである。
        occurrences = text.count(old)
        if occurrences != 1:
            missing.append((target, label, old, occurrences))
            print(f"  STALE {target}: {label} (found {occurrences}x, need exactly 1)")
            continue
        if run_selftest(p, text.replace(old, new, 1)):
            survived.append((target, label, why))
            print(f"  SURVIVED {target}: {label}")
        else:
            print(f"  killed   {target}: {label}")

    if missing:
        print(
            "\nSome mutations do not apply cleanly. 0 occurrences means the mutation ran "
            "against an unmutated file and proved nothing; 2+ means only the first was "
            "patched, so a partially broken detector may still fail its selftest and be "
            "reported as covered. Update the mutation to match the current source.",
            file=sys.stderr,
        )
        for target, label, old, count in missing:
            print(f"  {target}: {label} — found {count}x: {old}", file=sys.stderr)
        return 1

    if survived:
        print(
            "\nSome mutations survived. The selftest still passed with the detector "
            "broken, so that guard is not covered by any test case. Add a case that "
            "fails under the mutation — for a widened match that means a NEGATIVE "
            "case (a legitimate string containing the pattern as a substring).",
            file=sys.stderr,
        )
        for target, label, why in survived:
            print(f"  {target}: {label}\n    would break: {why}", file=sys.stderr)
        return 1

    print(f"\nall {len(MUTATIONS)} mutation(s) killed across {len(targets)} detector(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
