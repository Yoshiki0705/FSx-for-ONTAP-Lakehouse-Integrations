#!/usr/bin/env python3
r"""FSx の名称規約を、追跡下の全ファイルに対して検査する。既存分は縮む一方の負債リストで持つ。

**背景。** AGENTS.md は「``FSxN``・裸の ``FSx``・``FSx ONTAP`` は使わない」と書く。しかし
agent-output-audit.yml の既存ステップが見るのは 3 つのリテラル（``FSxN`` / ``FSx ONTAP`` /
``FSx S3 AP``）だけで、対象も**変更された .md** に限られていた。裸の ``FSx`` は検査されず、
シェル・YAML・JSON・テキストも、変更されていないファイルも見ていなかった（Issue #132）。
規約を書く側と検査する側が食い違うと、規約は覚えている間だけ守られるものになる。

**規則。** Hub の ``tools/audit_public_output.py`` の naming 規則に合わせる。

  - 裸の ``FSx`` を違反とする。許可するのは ``Amazon FSx``（公式のファミリー名）、
    ``FSx for ONTAP`` / ``FSx for NetApp ONTAP``、``FSx for Windows|Lustre|OpenZFS``、
    ``FSx-for-ONTAP`` のスラッグ、ファイル名、識別子の文脈（``AWS::FSx``、``FSx:`` など）。
    URL とコードスパンは散文ではないので見ない。
  - 使ってはならない綴り（``FSxN`` / ``FSx ONTAP`` / ``FSx NetApp`` / ``FSx S3 AP``）は常に
    違反。これは識別子ではなく綴りの引用なので、コードスパンの中でも違反とする。見ないのは
    URL の中だけ。``Amazon FSx ONTAP`` も違反（``Amazon`` は ``for`` の欠落を許さない）。
    この綴りは裸の ``FSx`` としては数えない（二重に数えると負債の件数が実態の倍になる）。
  - 数えるのは出現ごと。1 行に 2 つあれば 2 件。

Hub の監査器との違いは 3 点ある。

  1. 行をまたぐ製品名を 1 つの名前として読む（下の「折り返し」）。現在のツリーでは、折り返された
     正しい名前 3 行（``FSx for`` の次の行が ``ONTAP``）が Hub の行ごとの読みでは違反になる。
  2. URL は ASCII の URL 文字だけで終わる。Hub の ``\S+`` は、空白を置かない日本語の組版で
     URL の直後の本文まで URL として飲み込み、その中の ``FSx`` を見落とす。現在のツリーでは
     件数を変えない（測定済み）。
  3. ``FSxN`` の境界と識別子の窓の ``fsx-`` に ``\b`` を使わない（下の「境界」）。Hub の
     ``\bFSxN\b`` は ``FSxNを使う`` と ``構成でFSxN`` を見落とす。現在のツリーでは、この
     2 例を挙げて境界の不具合を説明する 2 行（AGENTS.md と agent-output-audit.yml）が
     新たに違反になり、どちらも許可マーカーを付けてある。

**走査範囲。** git の追跡下にある ``.md .txt .yml .yaml .json .sh``（Hub の監査器と同じ集合）。
git が公開物の範囲を決めているので、追跡下のファイルは除外せず全部見る。git が使えないときは
別の範囲に切り替えず、失敗にする。走査したファイルの集合は、ファイルシステムを直接歩いた
結果と毎回突き合わせ、ワークフローの ``paths:`` が走査対象の拡張子を全部覆っているかも
毎回確かめる（覆っていなければ、そのファイルの変更ではゲートが起動しない）。

**境界。** Python の ``\b`` は CJK を語構成文字とみなすため、``FSxを使う`` と ``構成でFSx`` の
片端ずつが無言になる。ASCII の英数字と ``_`` に隣接しないことで判定する。``_`` はクラスに残す
（``FSxN_OnPre`` のような構成名は散文の違反ではない）。

**折り返し。** 製品名は行をまたいで書かれる（``FSx for`` の次の行が ``ONTAP``）。行ごとに読むと
正しい名前を違反と読み、``Amazon`` の次の行が ``FSx`` という許可形も取りこぼす。一致が行の端に
接しているとき、隣の行を（コメント記号 ``#`` と引用記号 ``>`` を除いて）同じ文の続きとして読む。
空行・リスト項目・コードフェンスをまたいでは読まない。

**負債。** この検査が置かれる前から残っている出現は ``scripts/fsx-naming-debt.txt`` に
``<path> <count>`` で持つ。件数は正確でなければならず、**どちら向きの変動も失敗**にする。
増えれば新しい負債、減れば数字を下げる（0 になれば行を消す）。これで一覧は縮む一方になる。
足す・上げるはレビューアが見るべき判断で、検査は通さない。

**許可マーカー。** 逐語引用など正当な 1 行には ``<!-- allow:naming: 理由 -->`` を付ける。
コードスパンの中とコードフェンスの中のマーカーは構文の例であって指令ではない。何も抑制して
いないマーカーは失敗にする。残すと、その行に将来入る違反を黙って通す。

使い方:
  python3 scripts/check-fsx-naming.py --selftest    # 検査が落ちる能力の確認
  python3 scripts/check-fsx-naming.py               # 本検査
  python3 scripts/check-fsx-naming.py --print-debt  # 現状の件数を負債ファイルの書式で出す
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
DEBT_FILE = ROOT / "scripts" / "fsx-naming-debt.txt"
WORKFLOW = ROOT / ".github" / "workflows" / "agent-output-audit.yml"

# Hub の監査器（tools/audit_public_output.py の SCAN_SUFFIXES）と同じ集合。.py と .sql は
# 見ない。変えるときは WORKFLOW の paths（push と pull_request の両方）も変える。両者の
# 一致は毎回の実行で検査する。
SCAN_SUFFIXES = frozenset({".md", ".txt", ".yml", ".yaml", ".json", ".sh"})

# ---------------------------------------------------------------------------- 規則
ASCII_L = r"(?<![A-Za-z0-9_])"
ASCII_R = r"(?![A-Za-z0-9_])"
BARE = re.compile(ASCII_L + "FSx" + ASCII_R)
# 使ってはならない綴り。裸の FSx と違い、コードスパンの中でも違反にする。識別子ではなく
# 綴りの引用だから（Hub の監査器と、既存の変更 .md 向けステップの両方がそう読む）。
FORM = re.compile(ASCII_L + r"(?:FSxN|FSx[ \t]+(?:ONTAP|NetApp|S3[ \t]+AP))" + ASCII_R)

AMAZON_BEFORE = re.compile(r"Amazon\s$")
AMAZON_EOL = re.compile(r"Amazon$")
FOR_ONTAP = re.compile(r"\s+for\s+(?:NetApp\s+)?ONTAP")
FOR_SIBLING = re.compile(r"\s+for\s+(?:Windows|Lustre|OpenZFS)")
SLUG = re.compile(r"-for-ONTAP")
FILENAME = re.compile(r"[-\w]*\.(?:md|py|ya?ml|json|svg|png|drawio)")
ONTAP_NEXT = re.compile(r"\s+ONTAP")
# 識別子の文脈。FSx の前後 12 文字の窓で探す（Hub の監査器と同じ幅）。
IDENT = re.compile(
    r"FSx[A-Za-z0-9_]*\s*[=:]|AWS::FSx|aws\s+fsx|" + ASCII_L + r"fsx-|FSxOntap|FSX_"
)

# URL は ASCII の URL 文字だけ。空白・括弧・引用符・CJK で終わる。
URL = r"https?://[A-Za-z0-9._~:/?#@!$&*+,;=%-]+"
CODE_SPAN = re.compile(r"`[^`]*`")
NON_PROSE = re.compile(URL + "|" + CODE_SPAN.pattern)
URL_ONLY = re.compile(URL)

ALLOW_NAMING = re.compile(r"<!--[^>]*?allow:naming[^>]*?-->")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
CONT_PREFIX = re.compile(r"^[ \t]*(?:[#>][ \t]*)*")

TEXT, FENCE_LINE, FENCED = "text", "fence", "fenced"


class Finding(NamedTuple):
    line: int  # 1 始まり
    kind: str  # "bare" | "form"
    hint: str


def line_roles(lines: list[str]) -> list[str]:
    """各行が本文・フェンスの区切り・フェンスの中のどれかを返す。

    フェンスの開閉は Hub の監査器と同じ規則（開いた記号と同じ種類で、同じ長さ以上の
    記号だけの行で閉じる）。フェンスの中も走査する。コマンド例のコメントは散文だから。
    """
    roles: list[str] = []
    opened: str | None = None
    for line in lines:
        m = FENCE.match(line)
        if opened is None:
            roles.append(FENCE_LINE if m else TEXT)
            if m:
                opened = m.group(1)
        elif m:
            roles.append(FENCE_LINE)
            # 閉じ行は、開いた記号だけでできていて、開いた行以上の長さを持つ。記号だけで
            # できているという条件が、記号の種類の一致も含んでいる。
            if len(m.group(1)) >= len(opened) and set(line.strip()) == {opened[0]}:
                opened = None
        else:
            roles.append(FENCED)
    return roles


def _blank(match: re.Match[str]) -> str:
    """一致を同じ長さの空白にする。桁位置と ``Amazon `` の直前判定が崩れない。"""
    return " " * len(match.group())


def _marker_view(line: str) -> str:
    """マーカーの有無を判定する行。コードスパンは落とす。

    **マーカーを説明している行が、マーカーとして数えられてはいけない。** 構文例を
    バッククォートで囲んだ行を本物と誤認すると、説明している行が自分を検査から外す。
    """
    return CODE_SPAN.sub("", line)


def has_marker(line: str, role: str) -> bool:
    """この行が実効のマーカーを持つか。フェンスの中は指令ではない。"""
    return role == TEXT and ALLOW_NAMING.search(_marker_view(line)) is not None


def _following(views: list[str], i: int, limit: int = 3) -> str:
    """行 i の後ろに続く行（最大 limit 行）を、改行で区切って連結する。

    ``FSx for NetApp ONTAP`` を全部の空白で折ると、FSx の後ろに 3 行が続く。空行と、
    コメント記号を除くと空になる行で止める（段落の切れ目を越えない）。コードフェンスの
    区切り行の view は空なので、フェンスもここで止まる。リスト項目の ``-`` や表の ``|`` は
    取り除かないので、そこでも続きとは読まれない。
    """
    out: list[str] = []
    for j in range(i + 1, min(i + 1 + limit, len(views))):
        body = CONT_PREFIX.sub("", views[j], count=1)
        if not body.strip():
            break
        out.append("\n" + body)
    return "".join(out)


def _form_hint(spelling: str) -> str:
    """使ってはならない綴りごとの直し方。"""
    if spelling.endswith("NetApp"):
        return "write 'Amazon FSx for NetApp ONTAP'"
    # ONTAP も AP で終わるので、S3 の後ろの AP かどうかで見る。
    if re.search(r"S3[ \t]+AP$", spelling):
        return "write 'FSx for ONTAP S3 Access Points'"
    return "write 'FSx for ONTAP'"


def _bare_hint(views: list[str], i: int, m: re.Match[str]) -> str | None:
    """裸の FSx の一致が違反なら直し方を、許可形なら None を返す。"""
    line = views[i]
    start, end = m.span()
    if IDENT.search(line[max(0, start - 12) : end + 12]):
        return None
    left = line[:start]
    if AMAZON_BEFORE.search(left):
        return None
    # 行の最初の語が FSx で、前の行が Amazon で終わっていれば同じ名前。
    starts_line = not CONT_PREFIX.sub("", left, count=1).strip()
    if i > 0 and starts_line and AMAZON_EOL.search(views[i - 1].rstrip()):
        return None
    right = line[end:] + _following(views, i)
    if (
        FOR_ONTAP.match(right)
        or FOR_SIBLING.match(right)
        or SLUG.match(right)
        or FILENAME.match(right)
    ):
        return None
    if ONTAP_NEXT.match(right):
        return "write 'FSx for ONTAP' (the word 'for' is missing)"
    return (
        "write 'Amazon FSx' when the Amazon FSx service is meant, "
        "'FSx for ONTAP' when the file system is"
    )


def scan(text: str, *, honour_markers: bool = True) -> list[Finding]:
    """本文の違反を出現ごとに返す。

    ``honour_markers=False`` は、マーカーが実際に何かを抑制しているかを測るために使う。
    マーカーのテキストを落としたうえで走査するので、理由欄に書いた語は数えない。
    """
    lines = text.split("\n")
    roles = line_roles(lines)
    marked = [has_marker(ln, r) for ln, r in zip(lines, roles)]
    if not honour_markers:
        lines = [ALLOW_NAMING.sub("", ln) if m else ln for ln, m in zip(lines, marked)]
    views = [
        "" if r == FENCE_LINE else NON_PROSE.sub(_blank, ln)
        for ln, r in zip(lines, roles)
    ]
    links = [
        "" if r == FENCE_LINE else URL_ONLY.sub(_blank, ln)
        for ln, r in zip(lines, roles)
    ]
    found: list[Finding] = []
    for i, role in enumerate(roles):
        if role == FENCE_LINE or (honour_markers and marked[i]):
            continue
        forms: set[int] = set()
        for f in FORM.finditer(links[i]):
            forms.add(f.start())
            found.append(Finding(i + 1, "form", _form_hint(f.group())))
        for m in BARE.finditer(views[i]):
            if m.start() in forms:
                continue  # 同じ綴りを上で報告した
            hint = _bare_hint(views, i, m)
            if hint:
                found.append(Finding(i + 1, "bare", hint))
    return found


def inert_markers(text: str) -> list[int]:
    """何も抑制していないマーカーの行番号を返す。

    **マーカーは主張である**（この行は逐語引用だ、という主張）。引用を書き換えれば主張は
    無効になるが、マーカーは残る。残ったマーカーは、その行に将来入り込む違反を黙って通す。
    縮むしかない性質が無い抑制は、抑制ではなく永久の穴になる。
    """
    lines = text.split("\n")
    roles = line_roles(lines)
    flagged = {f.line for f in scan(text, honour_markers=False)}
    return [
        n
        for n, (ln, r) in enumerate(zip(lines, roles), 1)
        if has_marker(ln, r) and n not in flagged
    ]


# ---------------------------------------------------------------------------- 負債
class Verdict(NamedTuple):
    new: list[str]  # 件数があるのに一覧に無い
    more: list[tuple[str, int, int]]  # (path, 一覧の件数, 実際の件数) 実際が多い
    fewer: list[tuple[str, int, int]]  # 実際が少ない（0 は含まない）
    gone: list[str]  # 一覧にあるが件数が 0（消えたファイルを含む）


def judge(counts: dict[str, int], debt: dict[str, int]) -> Verdict:
    """実際の件数と負債リストを突き合わせる。**どちら向きの変動も違反。**

    増えるのは新しい負債。減るのに数字を下げないと、空いた枠に新しい違反が入っても
    通る。0 になった行を残すと、そのファイルは以後どんな違反も報告されなくなる。
    """
    new = [p for p in sorted(counts) if counts[p] > 0 and p not in debt]
    more = [(p, debt[p], counts[p]) for p in sorted(debt) if counts.get(p, 0) > debt[p]]
    fewer = [
        (p, debt[p], counts[p]) for p in sorted(debt) if 0 < counts.get(p, 0) < debt[p]
    ]
    gone = [p for p in sorted(debt) if counts.get(p, 0) == 0]
    return Verdict(new, more, fewer, gone)


def parse_debt(text: str) -> tuple[dict[str, int], list[str]]:
    """``<path> <count>`` の行を読む。読めない行と重複は別に返す。"""
    debt: dict[str, int] = {}
    malformed: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, _, count = line.rpartition(" ")
        name = name.strip()
        # isdigit() は '²' のような ASCII 以外の数字も通し、int() が落ちる。
        if not name or not (count.isascii() and count.isdigit()) or name in debt:
            malformed.append(line)
            continue
        debt[name] = int(count)
    return debt, malformed


DEBT_HEADER = """\
# Pre-existing uses of a shortened Amazon FSx for NetApp ONTAP name, per file.
# Each line reads "<path> <count>". The counts are exact: the gate fails when a file has
# more than listed (new debt) and when it has fewer (lower the number; delete the line at 0).
# This file may only shrink. Fix the new text instead of adding or raising a line here.
# The rule, the allowed forms and the marker: the docstring of scripts/check-fsx-naming.py.
# Current counts in this format: python3 scripts/check-fsx-naming.py --print-debt
"""


def render_debt(counts: dict[str, int]) -> str:
    return DEBT_HEADER + "".join(f"{p} {counts[p]}\n" for p in sorted(counts))


# ---------------------------------------------------------------------- 走査範囲
def select_targets(names: Iterable[str]) -> list[str]:
    """追跡下のパスから走査対象を選ぶ。階層は問わない。拡張子は大文字小文字を区別しない。"""
    return sorted(n for n in names if Path(n).suffix.lower() in SCAN_SUFFIXES)


def tracked() -> list[str]:
    """git の追跡下のパス。取れなければ失敗にする。

    別の範囲（ディレクトリを歩く）に切り替えると、何を見たのかが結果から読めなくなる。
    ``-z`` を付けるのは、付けないと非 ASCII のパスが引用符付きで返り、そのファイルを
    黙って見落とすため。
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as exc:
        raise SystemExit(f"error: git ls-files failed ({exc})") from exc
    names = [n for n in out.split("\0") if n]
    if not names:
        raise SystemExit(
            "error: git ls-files returned no files; not reporting a clean tree"
        )
    return names


def walk_expected(root: Path, tracked_names: set[str]) -> set[str]:
    """ファイルシステムを直接歩いて、追跡下かつ対象拡張子のパスを集める。

    ``select_targets`` とは別の経路で期待値を作る。グロブの階層取りこぼしは、同じ経路で
    作った期待値には現れない。
    """
    found: set[str] = set()
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            rel = (Path(base) / f).relative_to(root).as_posix()
            if rel in tracked_names and os.path.splitext(f)[1].lower() in SCAN_SUFFIXES:
                found.add(rel)
    return found


def coverage_gaps(expected: Iterable[str], scanned: Iterable[str]) -> list[str]:
    """期待されるのに走査されていないパス。**ゲートが黙って飛ばしたファイル。**"""
    return sorted(set(expected) - set(scanned))


# ---------------------------------------------------------------- 起動条件の網羅
def _event_block(text: str, event: str) -> str | None:
    """ワークフローの ``on:`` 配下で、イベントのブロックの本文を返す。

    インデント幅は決め打ちにせず、見つけたキーの幅より深い行をブロックとして読む。
    読み損ねて None を返すと「絞り込みが無い」と同じ扱いになり、検査が無言になる。
    """
    lines = text.split("\n")
    for start, line in enumerate(lines):
        if line.startswith("jobs:"):
            return None
        m = re.fullmatch(rf"(\s+){re.escape(event)}:\s*(?:#.*)?", line)
        if m:
            break
    else:
        return None
    indent = len(m.group(1))
    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and len(line) - len(line.lstrip(" ")) <= indent:
            break
        block.append(line)
    return "\n".join(block)


def trigger_gaps(
    text: str,
    suffixes: Iterable[str],
    events: Iterable[str] = ("push", "pull_request"),
) -> list[str]:
    """``paths:`` が走査対象の拡張子を覆っていない箇所。

    **ゲートの成功は、ゲートが走った証拠ではない。** ワークフローが ``paths:`` で絞り込んで
    いると、走査対象の拡張子が漏れた変更ではそもそも起動しない。``paths:`` が無ければ
    絞り込みが無いので、漏れは無い。
    """
    missing: list[str] = []
    for event in events:
        block = _event_block(text, event)
        if block is None or "paths:" not in block:
            continue
        for suffix in sorted(suffixes):
            # 後ろは区切りを要求する（.md が .mdx で満たされない）。前の ! は除外指定。
            pattern = r"(?<!!)" + re.escape("**/*" + suffix) + r"""(?:['"\s,\]]|$)"""
            if not re.search(pattern, block):
                missing.append(f"{event}: paths has no '**/*{suffix}'")
    return missing


# ---------------------------------------------------------------------- 測定
class Survey(NamedTuple):
    counts: dict[str, int]
    findings: dict[str, list[Finding]]
    inert: dict[str, list[int]]
    unreadable: list[str]


def survey(targets: Iterable[str]) -> Survey:
    counts: dict[str, int] = {}
    findings: dict[str, list[Finding]] = {}
    inert: dict[str, list[int]] = {}
    unreadable: list[str] = []
    for name in targets:
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except FileNotFoundError:
            continue  # 索引には残っているが作業ツリーから消した（未ステージの削除）
        except (UnicodeDecodeError, OSError):
            unreadable.append(name)
            continue
        found = scan(text)
        if found:
            counts[name] = len(found)
            findings[name] = found
        stale = inert_markers(text) if "allow:naming" in text else []
        if stale:
            inert[name] = stale
    return Survey(counts, findings, inert, unreadable)


def _lines(found: list[Finding], limit: int = 20) -> list[str]:
    shown = [f"    L{f.line}: {f.hint}" for f in found[:limit]]
    if len(found) > limit:
        shown.append(f"    ... and {len(found) - limit} more")
    return shown


def report(verdict: Verdict, sv: Survey, malformed: list[str]) -> int:
    """違反を表示して終了コードを返す。0 は何も無い。"""
    err = sys.stderr
    problems = 0
    if sv.unreadable:
        problems += 1
        print("error: files the gate could not read as UTF-8:", file=err)
        for p in sv.unreadable:
            print(f"  {p}", file=err)
    if malformed:
        problems += 1
        print(f"error: {DEBT_FILE.name} lines must read '<path> <count>':", file=err)
        for line in malformed:
            print(f"  {line}", file=err)
    if sv.inert:
        problems += 1
        print(
            "error: allow:naming markers that suppress nothing. Delete them; a marker "
            "that stays lets the next violation on that line through:",
            file=err,
        )
        for p, nums in sorted(sv.inert.items()):
            print(f"  {p}: {', '.join(f'L{n}' for n in nums)}", file=err)
    if verdict.new:
        problems += 1
        print(
            "error: a shortened product name in files that are not on the debt list:",
            file=err,
        )
        for p in verdict.new:
            print(f"  {p}", file=err)
            print("\n".join(_lines(sv.findings[p])), file=err)
        print(
            f"\n  Fix the text. {DEBT_FILE.name} carries only what predates this gate and "
            "may only shrink; a quotation that must stay verbatim takes "
            "<!-- allow:naming: reason --> on its line.",
            file=err,
        )
    if verdict.more:
        problems += 1
        print(f"error: more occurrences than {DEBT_FILE.name} lists:", file=err)
        for p, listed, actual in verdict.more:
            print(f"  {p}: {actual} found, {listed} listed", file=err)
            print("\n".join(_lines(sv.findings[p])), file=err)
        print(
            "\n  Fix the new text rather than raising the number: raising it needs a "
            "reviewer to see it.",
            file=err,
        )
    if verdict.fewer:
        problems += 1
        print(f"error: fewer occurrences than {DEBT_FILE.name} lists:", file=err)
        for p, listed, actual in verdict.fewer:
            print(f"  {p}: {actual} found, {listed} listed", file=err)
        print(
            "\n  Lower the number. Otherwise the freed slots admit new occurrences "
            "without a failure.",
            file=err,
        )
    if verdict.gone:
        problems += 1
        print(
            f"error: {DEBT_FILE.name} lists files with no findings. Delete them:",
            file=err,
        )
        for p in verdict.gone:
            note = "" if (ROOT / p).is_file() else "  (no such file)"
            print(f"  {p}{note}", file=err)
    if problems:
        print(
            "\nCurrent counts in the debt-file format: "
            "python3 scripts/check-fsx-naming.py --print-debt",
            file=err,
        )
        return 1
    return 0


# ---------------------------------------------------------------------- selftest
# 両方向を証明する。落ちない検査は、検査が無いのと区別できない。
# (入力, 裸の FSx の件数, FSxN の件数)
DETECT_CASES: list[tuple[str, int, int]] = [
    # --- 境界。各端に「日本語隣接」と「空白付き ASCII」を組で置き、否定側も置く ---
    ("Use the FSx API.", 1, 0),
    ("FSxを使う", 1, 0),
    ("構成でFSx", 1, 0),
    ("構成でFSxを使う", 1, 0),
    ("XFSx", 0, 0),
    ("FSxOntap", 0, 0),
    ("FSx9", 0, 0),
    ("FSx_OnPre", 0, 0),
    ("pre_FSx", 0, 0),
    ("Use FSxN here.", 0, 1),
    ("FSxNを使う", 0, 1),
    ("構成でFSxN", 0, 1),
    ("FSxN_OnPre", 0, 0),
    ("XFSxN", 0, 0),
    ("FSxNN", 0, 0),
    # --- 使ってはならない綴り。裸の FSx と二重に数えない。語尾の境界も試す ---
    ("Use FSx ONTAP here.", 0, 1),
    ("Use FSx  ONTAP here.", 0, 1),
    ("Use FSx NetApp ONTAP here.", 0, 1),
    ("Use FSx S3 AP here.", 0, 1),
    ("Amazon FSx ONTAP", 0, 1),
    ("FSx ONTAPs", 1, 0),
    ("FSx S3 APIs", 1, 0),
    ("XFSx ONTAP", 0, 0),
    ("FSx S3 Access Point", 1, 0),
    # コードスパンの中でも、綴りの引用は違反（識別子ではない）。裸の FSx は違反にならない。
    ("the `FSx ONTAP` spelling", 0, 1),
    ("the `FSx NetApp` spelling", 0, 1),
    ("the `FSx S3 AP` spelling", 0, 1),
    ("see https://example.com/FSx-ONTAP-notes", 0, 0),
    # --- 許可形 ---
    ("Amazon FSx API", 0, 0),
    ("FSx for ONTAP", 0, 0),
    ("FSx for NetApp ONTAP", 0, 0),
    ("Amazon FSx for NetApp ONTAP", 0, 0),
    ("FSx for Windows File Server", 0, 0),
    ("FSx for Lustre", 0, 0),
    ("FSx for OpenZFS", 0, 0),
    ("the FSx-for-ONTAP-Adoption-Playbook repo", 0, 0),
    ("see FSx-notes.md", 0, 0),
    ("Type: AWS::FSx::FileSystem", 0, 0),
    ("FSx: enabled", 0, 0),
    ("FSx = enabled", 0, 0),
    # 識別子の文脈は、前後 12 文字の窓にある別の語で決まる。窓の中の語ごとに 1 件ずつ
    # 置く（どれか 1 つの語が他の語に隠れて試されないままになるのを避ける）。
    ("the AWS::FSx type", 0, 0),
    ("aws fsx for FSx", 0, 0),
    ("fsx-ontap FSx API", 0, 0),
    ("FSxOntap FSx API", 0, 0),
    ("FSX_ID FSx API", 0, 0),
    # --- 許可形に見えて違反 ---
    ("FSx for Amazon", 1, 0),
    ("service: FSx", 1, 0),
    # --- 散文ではない領域 ---
    ("`FSx` is quoted", 0, 0),
    ("run `aws fsx describe-file-systems`", 0, 0),
    ("see https://example.com/FSx/api for details", 0, 0),
    ("see https://example.com/FSxN-lambda for details", 0, 0),
    # FSxN はコードスパンの中でも違反。FSx はコードスパンの中なら識別子とみなす。
    ("the `FSxN` option", 0, 1),
    # URL は ASCII の URL 文字で終わる。直後の本文は散文。
    ("(https://docs.example.com/a)FSx API", 1, 0),
    ("https://example.com/xを参照FSxの設定", 1, 0),
    # --- 数え方は出現ごと ---
    ("FSx and FSx", 2, 0),
    ("FSx\nFSx", 2, 0),
    # --- フェンスの中も走査する。マーカーはフェンスの中では指令ではない ---
    ("```bash\n# create FSx volume\n```", 1, 0),
    ("~~~\nFSx\n~~~\nFSx", 2, 0),
    ("```\nFSx API <!-- allow:naming -->\n```", 1, 0),
    # フェンスは、同じ記号で同じ長さ以上の、記号だけの行でしか閉じない。閉じ方を誤ると
    # 中のマーカーが指令になる（ここでは中の行が走査されること自体は変わらない）。
    ("````\n```\nFSx API <!-- allow:naming -->\n```\n````", 1, 0),
    ("```\n~~~\nFSx API <!-- allow:naming -->\n~~~\n```", 1, 0),
    ("```\n```bash\nFSx API <!-- allow:naming -->\n```", 1, 0),
    # --- マーカー ---
    ("Quote: FSx S3 AP <!-- allow:naming: verbatim -->", 0, 0),
    ("`<!-- allow:naming -->` FSx API", 1, 0),
    ("FSx API <!-- allow:other -->", 1, 0),
    # --- 折り返し。コメント記号と引用記号は続きの目印 ---
    ("The FSx for\nONTAP volume.", 0, 0),
    ("# The FSx for\n# ONTAP volume.", 0, 0),
    ("> The FSx for\n> ONTAP volume.", 0, 0),
    ("Amazon\nFSx API", 0, 0),
    ("# Amazon\n# FSx API", 0, 0),
    # --- 折り返しの外側。段落・項目・フェンスをまたいで読まない ---
    ("The FSx for\n\nONTAP volume.", 1, 0),
    ("Amazon\n\nFSx API", 1, 0),
    ("uses FSx\n- for ONTAP", 1, 0),
    ("- Amazon\n- FSx", 1, 0),
    ("Amazon.\nFSx API", 1, 0),
    ("```\nFSx for\n```\nONTAP", 1, 0),
    # 最初の行の「前の行」は存在しない。添字 -1 が最後の行を指して読まれてはいけない。
    ("FSx API\nAmazon", 1, 0),
    # 識別子の窓は行頭で負にならない。窓が行末側へ回り込むと、短くない行で
    # 行頭の ``FSx:`` を見失う。
    ("FSx: enabled in the console settings", 0, 0),
]

# 折り返しに対する不変条件。**行ごとの数え方は違反の数ではない。** 同じ文をどこで
# 折っても（全部の空白で折っても）件数は変わらない。個別の期待値を並べるだけでは
# 「この折り方では通る」ことしか分からない。
WRAP_BASES: list[tuple[str, int]] = [
    ("Use Amazon FSx API calls here.", 0),
    ("Use FSx API calls here.", 1),
    ("The FSx for ONTAP volume is mounted.", 0),
    ("The FSx for NetApp ONTAP file system.", 0),
    ("FSx for Windows File Server is a sibling.", 0),
    ("Configure FSx ONTAP for production.", 1),
    ("Configure FSx NetApp ONTAP for production.", 1),
    ("Pass the FSx S3 AP alias.", 1),
    ("Pass the FSx S3 Access Point alias.", 1),
    ("Amazon FSx for NetApp ONTAP is the product.", 0),
]
WRAP_PREFIXES = ["", "# ", "> ", "  "]

# (入力, 実効のマーカーが何も抑制していない行番号)
MARKER_CASES: list[tuple[str, list[int]]] = [
    ("FSx API <!-- allow:naming -->", []),
    ("Amazon FSx API <!-- allow:naming -->", [1]),
    ("plain text <!-- allow:naming -->", [1]),
    # 理由欄に禁止語を書いても、それでマーカーが何かを抑制していることにはならない。
    ("Amazon FSx <!-- allow:naming: quoting FSxN -->", [1]),
    ("```\nAmazon FSx <!-- allow:naming -->\n```", []),
    ("`<!-- allow:naming -->` Amazon FSx", []),
]

HINT_CASES: list[tuple[str, str]] = [
    ("Use FSx ONTAP here", "write 'FSx for ONTAP'"),
    ("Use FSx\nONTAP here", "'for' is missing"),
    ("Use FSx NetApp ONTAP here", "Amazon FSx for NetApp ONTAP"),
    ("Use FSx S3 AP here", "S3 Access Points"),
    ("Use FSx API here", "Amazon FSx"),
    ("Use FSxN here", "write 'FSx for ONTAP'"),
]

# (件数, 負債, 期待する Verdict の (new, more, fewer, gone))
JUDGE_CASES: list[tuple[dict[str, int], dict[str, int], tuple]] = [
    ({}, {}, ([], [], [], [])),
    ({"a": 2}, {"a": 2}, ([], [], [], [])),
    ({"a": 1}, {}, (["a"], [], [], [])),
    ({"a": 3}, {"a": 2}, ([], [("a", 2, 3)], [], [])),
    ({"a": 1}, {"a": 2}, ([], [], [("a", 2, 1)], [])),
    ({}, {"a": 2}, ([], [], [], ["a"])),
    ({"a": 0}, {"a": 2}, ([], [], [], ["a"])),
    (
        {"a": 1, "b": 4, "c": 2},
        {"b": 3, "c": 5, "d": 1},
        (["a"], [("b", 3, 4)], [("c", 5, 2)], ["d"]),
    ),
]

# (入力, (負債, 読めない行))
PARSE_CASES: list[tuple[str, tuple[dict[str, int], list[str]]]] = [
    ("# note\n\ndocs/a.md 3\n", ({"docs/a.md": 3}, [])),
    ("docs/a b.md 2", ({"docs/a b.md": 2}, [])),
    ("docs/a.md", ({}, ["docs/a.md"])),
    ("docs/a.md x", ({}, ["docs/a.md x"])),
    ("docs/a.md -1", ({}, ["docs/a.md -1"])),
    ("docs/a.md ²", ({}, ["docs/a.md ²"])),
    ("docs/a.md 2\ndocs/a.md 3", ({"docs/a.md": 2}, ["docs/a.md 3"])),
]

# 深い階層・大文字の拡張子・拡張子の無い名前。
TARGET_NAMES = [
    "README.md",
    "docs/en/guide.md",
    "a/b/c/d/e/deep.sh",
    "NOTES.MD",
    "cfg.JSON",
    "data.txt",
    "t.yaml",
    "t.yml",
    "x.py",
    "y.sql",
    "z.ts",
    ".md",
    "Makefile",
]
TARGET_EXPECTED = [
    "NOTES.MD",
    "README.md",
    "a/b/c/d/e/deep.sh",
    "cfg.JSON",
    "data.txt",
    "docs/en/guide.md",
    "t.yaml",
    "t.yml",
]

COVERAGE_CASES: list[tuple[set[str], set[str], list[str]]] = [
    ({"a/b/c.md"}, set(), ["a/b/c.md"]),
    ({"a.md", "x/y.sh"}, {"a.md"}, ["x/y.sh"]),
    ({"a.md"}, {"a.md"}, []),
    (set(), {"x.md"}, []),
]

_NO_VERDICT = Verdict([], [], [], [])
_NO_SURVEY = Survey({}, {}, {}, [])
_ONE = {"a.md": [Finding(2, "bare", "fix it")]}
# (ラベル, Verdict, Survey, 読めない負債行, 終了コード, 標準エラーに含まれる断片)
REPORT_CASES: list[tuple[str, Verdict, Survey, list[str], int, str]] = [
    ("clean", _NO_VERDICT, _NO_SURVEY, [], 0, ""),
    ("unreadable", _NO_VERDICT, Survey({}, {}, {}, ["a.md"]), [], 1, "could not read"),
    ("malformed debt line", _NO_VERDICT, _NO_SURVEY, ["a.md"], 1, "must read"),
    ("inert marker", _NO_VERDICT, Survey({}, {}, {"a.md": [3]}, []), [], 1, "L3"),
    (
        "new",
        Verdict(["a.md"], [], [], []),
        Survey({"a.md": 1}, _ONE, {}, []),
        [],
        1,
        "not on the debt list",
    ),
    (
        "more",
        Verdict([], [("a.md", 1, 2)], [], []),
        Survey({"a.md": 2}, _ONE, {}, []),
        [],
        1,
        "2 found, 1 listed",
    ),
    (
        "fewer",
        Verdict([], [], [("a.md", 3, 1)], []),
        _NO_SURVEY,
        [],
        1,
        "1 found, 3 listed",
    ),
    ("gone", Verdict([], [], [], ["a.md"]), _NO_SURVEY, [], 1, "no findings"),
]

WORKFLOW_FULL = """\
on:
  push:
    branches: [main]
    paths: ['**/*.md', '**/*.txt', '**/*.yml', '**/*.yaml', '**/*.json', '**/*.sh']
  pull_request:
    branches: [main]
    paths: ['**/*.md', '**/*.txt', '**/*.yml', '**/*.yaml', '**/*.json', '**/*.sh']
  workflow_dispatch:
jobs:
  x: {}
"""
WORKFLOW_NO_TXT = WORKFLOW_FULL.replace("'**/*.txt', ", "")
WORKFLOW_BLOCK = """\
on:
  push:
    paths:
      - '**/*.md'
      - '**/*.txt'
      - '**/*.yml'
      - '**/*.yaml'
      - '**/*.json'
      - '**/*.sh'
  pull_request:
    paths:
      - '**/*.md'
jobs:
  x: {}
"""
WORKFLOW_UNFILTERED = (
    "on:\n  push:\n    branches: [main]\n  pull_request:\njobs:\n  x: {}\n"
)
# .mdx は .md ではない。
WORKFLOW_MDX = WORKFLOW_FULL.replace("'**/*.md'", "'**/*.mdx'")
# 除外指定（!）は覆っていることにならない。
WORKFLOW_NEGATED = WORKFLOW_FULL.replace("'**/*.txt'", "'!**/*.txt'")


def selftest() -> int:
    bad: list[str] = []
    total = 0

    def check(label: str, got: object, want: object) -> None:
        nonlocal total
        total += 1
        if got != want:
            bad.append(f"{label}: expected {want!r} got {got!r}")

    for text, bare, form in DETECT_CASES:
        found = scan(text)
        got = (
            sum(f.kind == "bare" for f in found),
            sum(f.kind == "form" for f in found),
        )
        check(f"detect {text!r}", got, (bare, form))

    for base, want in WRAP_BASES:
        words = base.split(" ")
        for prefix in WRAP_PREFIXES:
            variants = [prefix + base]
            for k in range(1, len(words)):
                head, tail = " ".join(words[:k]), " ".join(words[k:])
                variants.append(f"{prefix}{head}\n{prefix}{tail}")
            variants.append("\n".join(prefix + w for w in words))
            for v in variants:
                check(f"wrap-invariant {v!r}", len(scan(v)), want)

    for text, want in MARKER_CASES:
        check(f"inert markers {text!r}", inert_markers(text), want)

    for text, fragment in HINT_CASES:
        hints = [f.hint for f in scan(text)]
        check(f"hint {text!r}", any(fragment in h for h in hints), True)

    for counts, debt, want in JUDGE_CASES:
        check(f"judge {counts} vs {debt}", tuple(judge(counts, debt)), want)

    for text, want in PARSE_CASES:
        try:
            parsed: object = parse_debt(text)
        except ValueError as exc:  # 読めない行は例外ではなく malformed に回すこと
            parsed = f"raised {exc!r}"
        check(f"parse {text!r}", parsed, want)
    check(
        "render round-trips",
        parse_debt(render_debt({"b/x.md": 2, "a/y.sh": 1})),
        ({"a/y.sh": 1, "b/x.md": 2}, []),
    )

    check("select_targets", select_targets(TARGET_NAMES), TARGET_EXPECTED)

    for expected, scanned, want in COVERAGE_CASES:
        check(
            f"coverage {expected} vs {scanned}", coverage_gaps(expected, scanned), want
        )

    sfx = SCAN_SUFFIXES
    check("trigger: complete inline list", trigger_gaps(WORKFLOW_FULL, sfx), [])
    check(
        "trigger: .txt missing from both events",
        trigger_gaps(WORKFLOW_NO_TXT, sfx),
        ["push: paths has no '**/*.txt'", "pull_request: paths has no '**/*.txt'"],
    )
    check(
        "trigger: block list, pull_request lists only .md",
        len(trigger_gaps(WORKFLOW_BLOCK, sfx)),
        len(sfx) - 1,
    )
    check("trigger: no paths filter", trigger_gaps(WORKFLOW_UNFILTERED, sfx), [])
    check(
        "trigger: .mdx does not stand in for .md",
        trigger_gaps(WORKFLOW_MDX, sfx),
        ["push: paths has no '**/*.md'", "pull_request: paths has no '**/*.md'"],
    )
    check(
        "trigger: a negated pattern does not cover the suffix",
        trigger_gaps(WORKFLOW_NEGATED, sfx),
        ["push: paths has no '**/*.txt'", "pull_request: paths has no '**/*.txt'"],
    )

    # 負債ファイルの見出しは、それを読むこの検査に引っかかってはならない。
    check("debt header is clean", scan(DEBT_HEADER), [])

    # 走査範囲の期待値を作る別経路（ファイルシステムを歩く）が、同じ集合を返すこと。
    # 追跡下でないファイルと .git の中は含めない。
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for name in [*TARGET_NAMES, "untracked.md", ".git/HEAD.md"]:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        listed = {*TARGET_NAMES, ".git/HEAD.md"}
        check(
            "walk_expected",
            sorted(walk_expected(root, listed)),
            sorted(select_targets(TARGET_NAMES)),
        )

    # report は違反の種類ごとに非 0 を返し、直すべき箇所を標準エラーに出す。
    for label, verdict, sv, malformed, rc, fragment in REPORT_CASES:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            got = report(verdict, sv, malformed)
        check(f"report {label}: exit code", got, rc)
        check(f"report {label}: output", fragment in buf.getvalue(), True)

    for line in bad:
        print(f"selftest FAIL {line}", file=sys.stderr)
    if bad:
        return 1
    print(f"selftest: {total} case(s) passed")
    return 0


# ---------------------------------------------------------------------- 本検査
def main(argv: list[str]) -> int:
    known = {"--selftest", "--print-debt"}
    unknown = [a for a in argv if a not in known]
    if unknown:
        # 綴りの誤りで本検査が走ってしまう（あるいは何も検査されない）のを避ける。
        print(f"unknown argument(s): {' '.join(unknown)}", file=sys.stderr)
        return 2
    if "--selftest" in argv:
        return selftest()

    names = tracked()
    targets = select_targets(names)
    sv = survey(targets)

    if "--print-debt" in argv:
        sys.stdout.write(render_debt(sv.counts))
        return 1 if sv.unreadable else 0

    preflight: list[str] = []
    gaps = coverage_gaps(walk_expected(ROOT, set(names)), targets)
    if gaps:
        preflight.append(
            "tracked files the gate does not scan (the scan range is narrower "
            "than the tree):\n" + "\n".join(f"  {p}" for p in gaps)
        )
    if WORKFLOW.is_file():
        missing = trigger_gaps(WORKFLOW.read_text(encoding="utf-8"), SCAN_SUFFIXES)
        if missing:
            preflight.append(
                f"{WORKFLOW.relative_to(ROOT)} does not start on every scanned "
                "suffix, so a change to such a file would skip the gate:\n"
                + "\n".join(f"  {m}" for m in missing)
            )
    else:
        preflight.append(f"{WORKFLOW.relative_to(ROOT)} not found")
    if not DEBT_FILE.is_file():
        preflight.append(
            f"{DEBT_FILE.relative_to(ROOT)} not found. Create it from the current "
            "state: python3 scripts/check-fsx-naming.py --print-debt"
        )
    if preflight:
        for item in preflight:
            print(f"error: {item}", file=sys.stderr)
        return 1

    debt, malformed = parse_debt(DEBT_FILE.read_text(encoding="utf-8"))
    verdict = judge(sv.counts, debt)
    if report(verdict, sv, malformed):
        return 1
    carried = sum(sv.counts.values())
    print(
        f"fsx-naming: {len(targets)} file(s) scanned; {carried} occurrence(s) in "
        f"{len(sv.counts)} file(s) carried as debt in {DEBT_FILE.name}; "
        "no new ones"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
