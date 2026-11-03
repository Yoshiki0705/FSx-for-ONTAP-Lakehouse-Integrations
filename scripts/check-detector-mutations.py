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

**ただし、生き残りの原因がテストの不足とは限らない。** 条件 A が条件 B に含まれている
（B が成り立てば A も必ず成り立つ）とき、A を外す変異はどんなテストでも殺せない。実例:
コードフェンスを閉じる条件に「記号の種類が一致する」と「記号だけでできている」を並べていたが、
後者が前者を含んでいた。この場合に直すのはテストではなく、冗長な条件を消すこと。冗長な防御は
検出器の挙動を変えずに、テストの感度だけを下げる。

手で 2 通り回した確認は次回に残らない。ここに書けば残る。

使い方:
  python3 scripts/check-detector-mutations.py            # 全変異
  python3 scripts/check-detector-mutations.py --list     # 一覧のみ
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
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

# --- scripts/check-fsx-naming.py -------------------------------------------------
# (ラベル, 置換前, 置換後, この変異が表す実際の不具合)。対象は下で 1 か所にまとめる。
#
# 件数が多いのは、この検査の守りが多いから。境界の 6 通り（\b に戻す・外す・_ を落とす）は
# 前後の端ごとに別々に壊れ、一致範囲が広がる壊し方は否定ケースだけが止める。負債の判定は
# 4 つの分岐が独立していて、**1 つが欠けても実行結果は静かに正常に見える**（落ちないだけ）。
_FSX_NAMING_MUTATIONS: list[tuple[str, str, str, str]] = [
    (
        "leading guard -> Unicode \\b",
        'ASCII_L = r"(?<![A-Za-z0-9_])"',
        r'ASCII_L = r"\b"',
        "構成でFSx のように日本語が直前にある裸の FSx と FSxN を読めなくなる。"
        "\\b は CJK を語構成文字とみなす（AGENTS.md が名指しする元の不具合）",
    ),
    (
        "trailing guard -> Unicode \\b",
        'ASCII_R = r"(?![A-Za-z0-9_])"',
        r'ASCII_R = r"\b"',
        "FSxを使う のように日本語が直後に続く FSx を読めなくなる（もう一端）",
    ),
    (
        "leading guard removed (not replaced)",
        'ASCII_L = r"(?<![A-Za-z0-9_])"',
        'ASCII_L = r""',
        "XFSx のような長い語の末尾を FSx として拾う。一致範囲が広がるだけなので"
        "肯定ケースでは検出できない",
    ),
    (
        "trailing guard removed (not replaced)",
        'ASCII_R = r"(?![A-Za-z0-9_])"',
        'ASCII_R = r""',
        "FSx9 や FSxNN の先頭を拾う。同じく否定ケースだけが止める",
    ),
    (
        "leading guard drops _",
        'ASCII_L = r"(?<![A-Za-z0-9_])"',
        'ASCII_L = r"(?<![A-Za-z0-9])"',
        "pre_FSx のような識別子の一部を散文の違反として拾う",
    ),
    (
        "trailing guard drops _",
        'ASCII_R = r"(?![A-Za-z0-9_])"',
        'ASCII_R = r"(?![A-Za-z0-9])"',
        "FSx_OnPre / FSxN_OnPre のような構成名（SVM 名）を散文の違反として拾う。"
        "AGENTS.md の「_ をクラスに残す」の根拠そのもの",
    ),
    (
        "Amazon FSx exemption removed",
        "if AMAZON_BEFORE.search(left):",
        "if False:",
        "公式のファミリー名 Amazon FSx を違反にする。負債が数百件増え、直せない一覧になる",
    ),
    (
        "Amazon FSx exemption ignores the previous line",
        "AMAZON_EOL.search(views[i - 1].rstrip())",
        "False",
        "Amazon の次の行が FSx という折り返しを違反にする",
    ),
    (
        "continuation lines are not read",
        "limit: int = 3",
        "limit: int = 0",
        "FSx for の次の行が ONTAP という折り返しを違反にする。Issue #132 のコメントが"
        "指摘した、行ごとの数え方が正しい名前を違反と読む不具合そのもの",
    ),
    (
        "FSx for ONTAP exemption removed",
        "FOR_ONTAP.match(right)",
        "False",
        "正しい名前 FSx for ONTAP を違反にする",
    ),
    (
        "sibling services exemption removed",
        "FOR_SIBLING.match(right)",
        "False",
        "FSx for Windows / Lustre / OpenZFS を違反にする",
    ),
    (
        "slug exemption removed",
        "SLUG.match(right)",
        "False",
        "リポジトリ名のスラッグ FSx-for-ONTAP-... を違反にする",
    ),
    (
        "file name exemption removed",
        "FILENAME.match(right)",
        "False",
        "FSx-notes.md のようなファイル名を違反にする",
    ),
    (
        "identifier context exemption removed",
        "if IDENT.search(line[max(0, start - 12) : end + 12]):",
        "if False:",
        "AWS::FSx::FileSystem や FSx: 設定値 の識別子を違反にする",
    ),
    (
        "identifier context: FSx<id>: / FSx<id> = removed",
        r'r"FSx[A-Za-z0-9_]*\s*[=:]|',
        'r"',
        "YAML・設定ファイルの FSx: キーや FSx = 代入を違反にする",
    ),
    (
        "identifier context: AWS::FSx removed",
        "|AWS::FSx|",
        "|",
        "CloudFormation のリソース型 AWS::FSx::... の近くの FSx を違反にする",
    ),
    (
        "identifier context: aws fsx removed",
        r"|aws\s+fsx|",
        "|",
        "CLI の aws fsx ... の近くの FSx を違反にする",
    ),
    (
        "identifier context: fsx- removed",
        '" + ASCII_L + r"fsx-|',
        '" + r"',
        "fsx-ontap-... のようなリソース名の接頭辞の近くの FSx を違反にする",
    ),
    (
        "identifier context: FSxOntap removed",
        "|FSxOntap|",
        "|",
        "FSxOntap... のようなプロパティ名の近くの FSx を違反にする",
    ),
    (
        "identifier context: FSX_ removed",
        '|FSX_"',
        '"',
        "FSX_FILE_SYSTEM_ID のような環境変数名の近くの FSx を違反にする",
    ),
    (
        "marker switch ignored when testing for inertness",
        "(honour_markers and marked[i])",
        "marked[i]",
        "マーカーを無視して測るはずの走査がマーカーを尊重し、全部のマーカーが不活性に見える",
    ),
    (
        "URLs are read as prose",
        'NON_PROSE = re.compile(URL + "|" + CODE_SPAN.pattern)',
        "NON_PROSE = re.compile(CODE_SPAN.pattern)",
        "引用元の URL に含まれる FSx を違反にする",
    ),
    (
        "code spans are read as prose",
        'NON_PROSE = re.compile(URL + "|" + CODE_SPAN.pattern)',
        "NON_PROSE = re.compile(URL)",
        "`aws fsx ...` や `FSx` のような識別子の引用を違反にする",
    ),
    (
        "forbidden spellings are read from the prose view",
        "FORM.finditer(links[i])",
        "FORM.finditer(views[i])",
        "コードスパンの中に引用した FSxN や FSx ONTAP を見落とす。綴りの引用は識別子ではない"
        "（Hub の監査器と既存のステップは、コードスパンの中でも違反にする）",
    ),
    (
        "a forbidden spelling is counted twice",
        "if m.start() in forms:",
        "if False:",
        "散文中の FSx ONTAP が綴りの規則と裸の FSx の規則の両方で数えられ、"
        "負債の件数が実際の倍になる",
    ),
    (
        "forbidden spelling: FSxN removed",
        r'r"(?:FSxN|FSx[ \t]+',
        r'r"(?:FSx[ \t]+',
        "FSxN（最も繰り返される違反）を見落とす",
    ),
    (
        "forbidden spelling: FSx ONTAP removed",
        "(?:ONTAP|NetApp|S3[ \\t]+AP)",
        "(?:NetApp|S3[ \\t]+AP)",
        "コードスパンの中の FSx ONTAP（for が無い）を見落とす",
    ),
    (
        "forbidden spelling: FSx NetApp removed",
        "(?:ONTAP|NetApp|S3[ \\t]+AP)",
        "(?:ONTAP|S3[ \\t]+AP)",
        "コードスパンの中の FSx NetApp を見落とす",
    ),
    (
        "forbidden spelling: FSx S3 AP removed",
        "(?:ONTAP|NetApp|S3[ \\t]+AP)",
        "(?:ONTAP|NetApp)",
        "コードスパンの中の FSx S3 AP（既存のステップが検査していた綴り）を見落とす",
    ),
    (
        "forbidden spelling: only a single space between the words",
        r"FSx[ \t]+(?:ONTAP",
        r"FSx[ ](?:ONTAP",
        "FSx  ONTAP のように空白が 2 つ以上、またはタブの綴りを見落とす",
    ),
    (
        "FSxN is read inside URLs",
        "URL_ONLY = re.compile(URL)",
        'URL_ONLY = re.compile(r"(?!)")',
        "FSxN を含む引用元 URL を違反にする",
    ),
    (
        "URL swallows the text that follows it",
        'URL = r"https?://[A-Za-z0-9._~:/?#@!$&*+,;=%-]+"',
        'URL = r"https?://\\S+"',
        "空白を置かない日本語の組版で、URL の直後の本文にある FSx を URL の一部として"
        "見落とす。Hub の監査器と同じ穴で、行を覆う範囲を広げるだけなので"
        "肯定ケースでは検出できない",
    ),
    (
        "fenced code is skipped",
        "if role == FENCE_LINE or (honour_markers and marked[i]):",
        "if role != TEXT or (honour_markers and marked[i]):",
        "コードフェンスの中を走査しない。コマンド例のコメントが検査から外れる"
        "（Hub の監査器は走査する）",
    ),
    (
        "marker in a code span counted as a real marker",
        'return CODE_SPAN.sub("", line)',
        "return line",
        "マーカーを説明している行がマーカーとして働く。説明が自分を検査対象から外す",
    ),
    (
        "marker in a fence counted as a real marker",
        "return role == TEXT and ALLOW_NAMING.search(_marker_view(line)) is not None",
        "return role != FENCE_LINE and ALLOW_NAMING.search(_marker_view(line)) is not None",
        "コードフェンスの中の構文例が指令として働き、その行の違反が免除される",
    ),
    (
        "inert marker never reported",
        "if has_marker(ln, r) and n not in flagged",
        "if has_marker(ln, r) and False",
        "引用を直したあとに残ったマーカーが永久に残り、その行に将来入る違反を黙って通す。"
        "抑制が縮むしかない性質を失う",
    ),
    (
        "marker text counted as content when testing for inertness",
        'ALLOW_NAMING.sub("", ln) if m else ln',
        "ln",
        "理由欄に書いた禁止語がマーカーを必要なものに見せ、不活性のマーカーを見逃す",
    ),
    (
        "one finding per line",
        'found.append(Finding(i + 1, "bare", hint))',
        'found.append(Finding(i + 1, "bare", hint))\n                break',
        "1 行に 2 件あっても 1 件と数える。既に違反のある行へ後から足した違反が、"
        "負債の枠を増やさずに通る",
    ),
    (
        "verdict ignores files that are not on the list",
        "new = [p for p in sorted(counts) if counts[p] > 0 and p not in debt]",
        "new = []",
        "一覧に無いファイルの違反が通る。この検査の主目的が失われる",
    ),
    (
        "verdict tolerates a count above the list",
        "more = [(p, debt[p], counts[p]) for p in sorted(debt) if counts.get(p, 0) > debt[p]]",
        "more = []",
        "一覧にあるファイルへ違反を足しても通る。枠の中でなら負債が増やせる",
    ),
    (
        "verdict tolerates a count below the list",
        "if 0 < counts.get(p, 0) < debt[p]",
        "if False",
        "直したのに数字を下げなくてよくなり、空いた枠へ新しい違反が入っても通る",
    ),
    (
        "verdict tolerates a listed file with no findings",
        "gone = [p for p in sorted(debt) if counts.get(p, 0) == 0]",
        "gone = []",
        "0 になった行が残り、そのファイルは以後どんな違反も報告されない。"
        "一覧が縮む一方になる仕掛けを失い、**実行結果は静かに正常に見える**",
    ),
    (
        "a blank line does not end a continuation",
        "if not body.strip():",
        "if False:",
        "段落やコードフェンスをまたいで次の文を続きと読み、別々の文の FSx と ONTAP を"
        "1 つの名前として許可する",
    ),
    (
        "comment and quote markers are not stripped from the next line",
        'CONT_PREFIX = re.compile(r"^[ \\t]*(?:[#>][ \\t]*)*")',
        'CONT_PREFIX = re.compile(r"^")',
        "YAML・シェルのコメントと引用ブロックの折り返しを続きと読めない",
    ),
    (
        "previous-line Amazon applies to any position on the line",
        'starts_line = not CONT_PREFIX.sub("", left, count=1).strip()',
        "starts_line = True",
        "リスト項目 - FSx の前の行が Amazon で終わっていれば許可する。別々の項目を"
        "1 つの名前と読む",
    ),
    (
        "first line reads the last line as its predecessor",
        "if i > 0 and starts_line",
        "if starts_line",
        "添字 -1 が文書の最後の行を指し、先頭の FSx が末尾の Amazon で許可される",
    ),
    (
        "identifier window can start before the line",
        "max(0, start - 12)",
        "start - 12",
        "窓の始まりが負になって行末側へ回り込み、行頭の FSx: を識別子と認識できない",
    ),
    (
        "fence closes on a shorter run",
        "len(m.group(1)) >= len(opened)",
        "True",
        "```` で開いたフェンスが入れ子の ``` で閉じ、中のマーカーが指令として働く",
    ),
    (
        "fence closes on a line that is not only fence characters",
        "set(line.strip()) == {opened[0]}",
        "True",
        "```bash のような開始行や、別の記号の行 ~~~ が閉じ行として働く",
    ),
    (
        "coverage oracle is case sensitive",
        "os.path.splitext(f)[1].lower()",
        "os.path.splitext(f)[1]",
        "期待値の側が大文字の拡張子を落とし、走査側の同じ取りこぼしと一致して"
        "取りこぼしが見えなくなる",
    ),
    (
        "targets: nested paths are skipped",
        "names if Path(n).suffix.lower()",
        'names if "/" not in n and Path(n).suffix.lower()',
        "2 階層目以降のファイルを黙って走査しない。グロブの階層取りこぼしと同じ型",
    ),
    (
        "targets: suffix match is case sensitive",
        "Path(n).suffix.lower()",
        "Path(n).suffix",
        "NOTES.MD のような大文字の拡張子を走査しない（Hub の監査器は区別しない）",
    ),
    (
        "coverage gaps never reported",
        "return sorted(set(expected) - set(scanned))",
        "return []",
        "走査から漏れた追跡下のファイルを報告しない。ゲートが緑のまま対象を黙って飛ばす",
    ),
    (
        "coverage oracle includes untracked files",
        "rel in tracked_names and ",
        "",
        "追跡下でないファイルを期待値に入れ、毎回「走査されていない」と誤報する",
    ),
    (
        "coverage oracle does not descend",
        'dirs[:] = [d for d in dirs if d != ".git"]',
        "dirs[:] = []",
        "階層を降りない期待値は、階層の取りこぼしを取りこぼす",
    ),
    (
        "trigger gaps never reported",
        "if not re.search(pattern, block):",
        "if False:",
        "paths: が走査対象の拡張子を覆っていなくても通る。その拡張子の変更ではゲートが起動しない",
    ),
    (
        "trigger: .mdx satisfies .md",
        r'''r"""(?:['"\s,\]]|$)"""''',
        '""',
        "接尾語の一致だけを見て、.mdx を .md の起動条件とみなす",
    ),
    (
        "trigger: a negated pattern counts as covering",
        'r"(?<!!)" + ',
        "",
        "除外指定 !**/*.txt を、.txt を覆っているとみなす",
    ),
    (
        "trigger: an unfiltered workflow reported as a gap",
        'if block is None or "paths:" not in block:',
        "if block is None:",
        "paths: が無い（絞り込みが無い）ワークフローを漏れとして報告し、直せない警告になる",
    ),
    (
        "debt file: non-ASCII digits accepted",
        "count.isascii() and ",
        "",
        "² のような数字で int() が落ち、検査が例外で止まる",
    ),
    (
        "debt file: duplicate path accepted",
        "or name in debt",
        "",
        "同じパスを 2 回書くと後の行が前の行を上書きし、枠を広げたことが見えない",
    ),
    (
        "report ignores unreadable files",
        "if sv.unreadable:",
        "if False:",
        "UTF-8 として読めないファイルを黙って飛ばす",
    ),
    (
        "report ignores malformed debt lines",
        "if malformed:",
        "if False:",
        "読めない負債の行を黙って捨て、その行が守るはずのファイルが新規扱いになる",
    ),
    (
        "report ignores inert markers",
        "if sv.inert:",
        "if False:",
        "検出は正しくても、不活性のマーカーが報告されず終了コードも 0 のまま",
    ),
    (
        "report ignores new files",
        "if verdict.new:",
        "if False:",
        "judge が新しい違反を見つけても、終了コードが 0 になる",
    ),
    (
        "report ignores counts above the list",
        "if verdict.more:",
        "if False:",
        "judge が増加を見つけても、終了コードが 0 になる",
    ),
    (
        "report ignores counts below the list",
        "if verdict.fewer:",
        "if False:",
        "judge が減少を見つけても、終了コードが 0 になる",
    ),
    (
        "report ignores listed files with no findings",
        "if verdict.gone:",
        "if False:",
        "judge が残った行を見つけても、終了コードが 0 になる",
    ),
]
MUTATIONS += [("scripts/check-fsx-naming.py", *m) for m in _FSX_NAMING_MUTATIONS]


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
    sources = {t: (ROOT / t).read_text(encoding="utf-8") for t in targets}

    # selftest の実行は互いに独立で、時間の大半は子プロセスの起動と待ちなので、並列に走らせる。
    # 変異が 20 件ほどの間は直列で 0.3 秒だったが、80 件近くなると 4 秒かかり、
    # 毎コミットの pre-commit に載せる前提（.githooks/pre-commit の手順 7）が崩れる。
    # 出力は結果を集めてから元の順に出すので、並列にしても行の順序は変わらない。
    with ThreadPoolExecutor() as pool:
        # 対照。変異前が通らないなら、以降の「落ちた」は変異のせいだと言えない。
        print("control: unmutated selftests must pass")
        controls = list(pool.map(lambda t: run_selftest(ROOT / t, sources[t]), targets))
        for t, passed in zip(targets, controls):
            if not passed:
                print(f"  FAIL {t}: selftest does not pass unmutated", file=sys.stderr)
                return 1
            print(f"  ok   {t}")

        print("\nmutations: each must make its selftest fail")
        plan = []
        for target, label, old, new, why in MUTATIONS:
            text = sources[target]
            # **出現回数を 1 に固定する。** 0 回なら変異なしで走って何も証明しない。2 回以上
            # だと ``replace(..., 1)`` は片方しか壊さないので、**部分的に壊れた検出器で
            # selftest が落ち、guard 全体が守られていると誤読する。** 弱い変異が「殺された」
            # と出るのは、生き残るより危険な向きの誤りである。
            occurrences = text.count(old)
            mutated = text.replace(old, new, 1) if occurrences == 1 else None
            plan.append((target, label, old, why, occurrences, mutated))
        outcomes = list(
            pool.map(
                lambda item: (
                    None if item[5] is None else run_selftest(ROOT / item[0], item[5])
                ),
                plan,
            )
        )

    survived = []
    missing = []
    for (target, label, old, why, occurrences, _), passed in zip(
        plan, outcomes
    ):
        if occurrences != 1:
            missing.append((target, label, old, occurrences))
            print(f"  STALE {target}: {label} (found {occurrences}x, need exactly 1)")
        elif passed:
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
