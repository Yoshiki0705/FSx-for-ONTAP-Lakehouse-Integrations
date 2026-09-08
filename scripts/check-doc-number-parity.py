#!/usr/bin/env python3
"""EN/JA ドキュメント対の間で、単位付きの数量が食い違っていないかを検査する。

**なぜ節構造の一致だけでは足りないか。** 既存の JA/EN parity 検査は ``^##`` の
本数を数える。節の数が合っていても、表の中の数値は独立に古くなる。実例:
``integrations/snowflake/docs/{en,ja}/snowpipe-verification-results.md`` は同じ表で
一方が「PutObject 5 GB 上限」、他方が「50 GB 上限」と書いていた。**節構造は一致
していたので、既存の検査は何も言わなかった。** 原因は翻訳の誤りではなく、2 つの
上限（1 パートあたりと 1 オブジェクト全体）を 1 つとして提示していた元の構造で、
**言語間の不一致がその構造の誤りを露出させた。**

**走査範囲も穴だった。** 既存の検査は ``docs/ja/*.md`` と ``docs/en/*.md`` だけを
見る。上記の食い違いは ``integrations/snowflake/docs/`` にあり、範囲の外だった。
このスクリプトは追跡下の全 EN/JA 対（``/en/`` ↔ ``/ja/`` の入れ替えと ``-ja.md``
接尾語の 2 つの規約）を対象にする。

対象の数量:
  - バイト単位（KB/MB/GB/TB/PB とその 2 進接頭辞）と、その速度形（``/s``）
  - パーセント

速度と容量は別の数量として扱う。``128 MB/s`` と ``128 MB`` は一致しない。

対象外の扱い:
  - コードフェンスの内側（コマンド例の値は散文の主張ではない）
  - ``<!-- allow:number-parity -->`` を付けた行（片方の言語にだけ意味がある数量）

使い方:
  python3 scripts/check-doc-number-parity.py --selftest   # 検査が落ちる能力の確認
  python3 scripts/check-doc-number-parity.py              # 本検査
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP = {
    ".git",
    "node_modules",
    "vendor",
    ".venv",
    "venv",
    "__pycache__",
    ".private",
    ".kiro",
    ".playwright-mcp",
}

FENCE = re.compile(r"^\s*(?:```|~~~)")
ALLOW = re.compile(r"<!--\s*allow:number-parity\s*-->")
CODE_SPAN = re.compile(r"`+[^`]*`+")


def effective(line: str) -> str:
    """コードスパンを落とした行を返す。マーカーの有無はこの結果で判定する。

    **マーカーを説明している行が、マーカーとして数えられてはいけない。** 構文例を
    バッククォートで囲んで書くと、素朴な検索では本物のマーカーと区別できない。害は
    2 方向に出る。

    - **うるさい側**: マーカーについて書いただけで「不当なマーカー」として落ちる。
    - **静かな側**: 同じ緩さが検査本体では抑制として効き、その行の違反が免除される。
      **説明している行が自分を検査対象から外す。**
    """
    return CODE_SPAN.sub("", line)


def has_effective_marker(text: str) -> bool:
    """フェンス外・コードスパン外に実効のマーカーがあるか。"""
    in_fence = False
    for line in text.split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence and ALLOW.search(effective(line)):
            return True
    return False

# 長いものを先に並べる。``MB`` を先に置くと ``MiB`` の ``Mi`` が食われる。
BYTE_UNITS = ["KiB", "MiB", "GiB", "TiB", "PiB", "KB", "MB", "GB", "TB", "PB"]

# **境界は ASCII に限る。** Python の ``\w`` は CJK に一致するため、``(?![\w])`` と
# 書くと ``100MB以上`` を弾く。**検査すべき日本語側でだけ沈黙する。** 実測では、
# この 1 文字の違いが 4 対を「差分なし」に見せていた。
QTY = re.compile(
    r"(?<![A-Za-z0-9_.])(\d[\d,]*(?:\.\d+)?)\s*"
    r"(" + "|".join(BYTE_UNITS) + r"|%)"
    r"(/s(?:ec)?|/秒)?"
    r"(?![A-Za-z0-9_])"
)


def quantities(text: str, honour_allow: bool = True) -> dict[str, list[int]]:
    """行番号付きで、単位付き数量を正規化して集める。フェンス内は無視する。

    ``honour_allow=False`` は許可マーカーを無視して集める。**マーカーが実際に何かを
    抑制しているかを測るため**に使う（下の ``inert_allow_markers``）。
    """
    found: dict[str, list[int]] = {}
    in_fence = False
    for n, line in enumerate(text.split("\n"), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or (honour_allow and ALLOW.search(effective(line))):
            continue
        for num, unit, rate in QTY.findall(line):
            # 桁区切りと単位前の空白を落とし、速度形は /s に寄せる。
            key = f"{num.replace(',', '')} {unit}{'/s' if rate else ''}"
            found.setdefault(key, []).append(n)
    return found


def _diff_count(en_text: str, ja_text: str, honour_allow: bool) -> int:
    qe = quantities(en_text, honour_allow)
    qj = quantities(ja_text, honour_allow)
    return len(qe.keys() - qj.keys()) + len(qj.keys() - qe.keys())


def unjustified_allow_markers(en_text: str, ja_text: str) -> bool:
    """対の許可マーカーが、抑制すべきものを抑制していないなら True。

    **マーカーが正当なのは、無視したときに報告が増える場合だけ。** つまり実際に片側だけの
    数量を隠しているとき。増えないなら 2 通りある。

    - 何も変えていない（不活性）。見出し側と同じで、残すとその行に将来入り込む食い違いを
      黙って通す。
    - **報告を減らすどころか増やしている。** 両言語が共有している数量にマーカーを付けると、
      片方から数量が消えて**存在しない食い違いが生まれる。** 不活性より悪い。

    最初の実装は「尊重した場合と無視した場合で同一か」で判定していて、後者を取り逃していた。
    **不活性だけを探すと、有害な側が通る。**

    対単位で判定する。数量の parity は対の性質なので、**1 行だけを見てそのマーカーが
    効いているかは決められない** — 相手側の内容に依存する。
    """
    if not (has_effective_marker(en_text) or has_effective_marker(ja_text)):
        return False
    return not (
        _diff_count(en_text, ja_text, False) > _diff_count(en_text, ja_text, True)
    )


def baseline_verdict(known: bool, has_diff: bool) -> str:
    """``KNOWN_DIVERGENT_PAIRS`` に載っているかと差分の有無から、対の扱いを決める。

    **``main()`` から切り出してあるのは、テストできるようにするため。** この 4 通りの
    うち ``stale`` は、一覧を縮むしかない状態に保つ唯一の仕掛けで、**それが効かなくても
    実行結果は静かに正常に見える**（落ちないだけ）。境界の guard と同じで、無言になる側の
    不具合なので、selftest とその mutation で押さえる。
    """
    if not has_diff:
        # 一覧に載っているのに差分が無い対は、一覧が古い証拠。放置するとその対は以後
        # どんな食い違いでも報告されなくなる。落として消させる。
        return "stale" if known else "clean"
    return "deferred" if known else "report"


def compare(en_text: str, ja_text: str) -> tuple[list, list]:
    """片方にしか現れない数量を返す。**本数の差は見ない。**

    同じ数量を EN が 3 回・JA が 2 回書くのは通常のことで、そこを見ると
    言い換えの差で埋め尽くされる。見るのは「一方にあって他方に無い」だけ。
    """
    qe, qj = quantities(en_text), quantities(ja_text)
    only_en = sorted((k, qe[k]) for k in qe.keys() - qj.keys())
    only_ja = sorted((k, qj[k]) for k in qj.keys() - qe.keys())
    return only_en, only_ja


# **既知の全体乖離**。下の対は数量が食い違うだけでなく、文書として別物になっている
# （節数と行数が大きく違う。例: ``10_slo_operational_readiness`` は EN 40 節 / JA 16 節、
# ``research.md`` は EN 871 行 / JA 2509 行）。**数量だけ揃えても意味が無い**ので、翻訳の
# 追いつきとして別途扱う。
#
# ここに置く理由は 2 つある。**新しい食い違いでこの検査が落ちるようにするため**と、
# **積み残しを数えられる状態に保つため。** 行ごとの ``<!-- allow:number-parity -->`` は
# 使わない。あのマーカーは「その数量は片方の言語にしか無い」という意味で、この 9 対に
# ついてはそれが嘘になる。
#
# **この一覧は縮める対象で、伸ばす対象ではない。** 対を直したら行を消すこと。消し忘れると
# 検査は無言のまま範囲を失う。
KNOWN_DIVERGENT_PAIRS = {
    "docs/en/unstructured-data-access.md",
    "docs/en/zero-copy-media-governance.md",
    "integrations/iceberg-metadata-catalog/demo/scenarios/industry-manufacturing.md",
    "integrations/iceberg-metadata-catalog/snowflake/etl-standard-glue-path/README.md",
    "integrations/manufacturing-data-platform/docs/en/08_design_concern_checklist.md",
    "integrations/manufacturing-data-platform/docs/en/10_slo_operational_readiness.md",
    "integrations/manufacturing-data-platform/docs/en/11_performance_targets_business_metrics.md",
    "integrations/snapmirror-flexcache-multicloud/docs/en/research.md",
    "integrations/snapmirror-flexcache-multicloud/docs/en/tc09-results.md",
}


def tracked() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "--", "*.md"],
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
        names = [n for n in out.split("\0") if n]
        if names:
            return names
    except (OSError, subprocess.CalledProcessError):
        pass
    return [
        str(p.relative_to(ROOT))
        for p in ROOT.rglob("*.md")
        if not any(part in SKIP for part in p.parts)
    ]


def pairs() -> list[tuple[str, str]]:
    """EN/JA 対を 2 つの規約で見つける。範囲は追跡下の全 Markdown。"""
    files = {f for f in tracked() if not any(part in SKIP for part in Path(f).parts)}
    out = []
    for f in sorted(files):
        if "/en/" in f:
            ja = f.replace("/en/", "/ja/", 1)
            if ja != f and ja in files:
                out.append((f, ja))
        elif not f.endswith("-ja.md"):
            ja = f[: -len(".md")] + "-ja.md"
            if ja in files:
                out.append((f, ja))
    return out


# 両方向を証明する。落ちない検査は、検査が無いのと区別できない。
# 1 件目は実際に起きた食い違いそのもの。
CASES: list[tuple[str, str, bool]] = [
    # (EN, JA, 差分を報告すべきか)
    ("| PutObject 5 GB ceiling |", "| PutObject 50 GB 上限 |", True),
    # --- 境界は前後の両方を試す ---
    # **片端だけ直すと、直したという記録だけが残る。** 後続 CJK（``100MB以上``）と先行 CJK
    # （``約100MB``）は別の lookaround が担当するので、両方に対を置く。
    #
    # 各対は「日本語隣接形」と「空白付き ASCII 形」を組にしてある。**日本語形だけを試すと、
    # 英語側の検出を壊す修正が通る。** 例えば境界を丸ごと外せば日本語形は通るが、
    # ``100MBps`` の誤検出が始まる。下の否定側の対がそれを止める。
    # 後続 CJK。
    ("point clouds (100 MB and up)", "点群（100MB以上）は", False),
    ("files 100MB and up", "ファイル 100 MB 以上", False),
    # 先行 CJK、空白なし。
    ("about 100 MB", "約100MB", False),
    ("a limit of 100 GB and up", "上限100GB以上", False),
    # 先行・後続ともに ASCII の語なら数量ではない。境界を外すとここが落ちる。
    ("throughput 100MBps sustained", "スループット 100MBps 維持", False),
    ("100MBps here", "ここは 100 MB", True),
    # **先行 guard の否定側。** 小数点の直後の数字を数量として読んではいけない。
    # guard を外すと ``.5 GB/s`` が ``5 GB/s`` になる — **10 倍の読み違い**で、
    # このスクリプトが防ごうとしている誤りと同じ型。mutation テストで、先行 guard を
    # 削る変異を殺しているのはこの 2 件だけ（``\b`` に替える変異は日本語ケースが殺す）。
    (".5 GB/s at the floor", "", False),
    ("ver2.5 GB of headroom", "", False),
    # 桁区切りと単位前の空白は正規化する。
    ("a 1,024 MB part", "1024MB のパート", False),
    # 容量と速度は別の数量。
    ("128 MB/s provisioned", "128 MB プロビジョンド", True),
    ("54.8 MB/s peak", "54.8 MB/秒 ピーク", False),
    # 2 進接頭辞と 10 進接頭辞は別の値。
    ("50 GiB per object", "1 オブジェクト 50 GB", True),
    # パーセントも対象。
    ("about 75% reduction", "約 75% の削減", False),
    ("about 75% reduction", "約 65% の削減", True),
    # 本数の差は報告しない。
    ("128 MB and 128 MB again", "128 MB は 1 回だけ", False),
    # フェンスの内側は無視する。
    ("```\n5 GB\n```\n", "", False),
    # 許可マーカーの付いた行は無視する。
    ("only here: 42 GB <!-- allow:number-parity -->", "", False),
    # **同じ緩さの静かな側。** マーカーをコードスパンで言及した行の数量は抑制されない。
    # 誤認すると、説明を書いた行の数値が検査から消える。
    ("`allow:number-parity` applies to 42 GB lines", "散文のみ", True),
    # 差分が無い対は無言で通る。
    ("50 GiB whole object, 5 GiB per part", "オブジェクト全体 50 GiB、1 パート 5 GiB", False),
]


# ``baseline_verdict`` の真理値表。**``stale`` の行が、一覧が縮むしかない性質を担う唯一の
# 仕掛け。** 抑制と保留を分けているのはこの 1 行なので、明示的に固定する。
BASELINE_CASES: list[tuple[bool, bool, str]] = [
    # (一覧に載っている, 差分がある, 期待する扱い)
    (False, True, "report"),
    (False, False, "clean"),
    (True, True, "deferred"),
    (True, False, "stale"),
]


# 許可マーカーの正当性。**不活性だけでなく「有害」側も要求する。** 2 件目が最初の実装で
# 取り逃していたケースで、これが無いと「不活性だけを探す」実装が通る。
MARKER_CASES: list[tuple[str, str, str, bool]] = [
    # (ラベル, EN, JA, 報告すべきか)
    ("justified", "only here: 42 GB <!-- allow:number-parity -->", "", False),
    (
        "harmful: invents a mismatch",
        "both say 128 MB <!-- allow:number-parity -->",
        "どちらも 128 MB",
        True,
    ),
    ("inert: no quantity on the line", "prose <!-- allow:number-parity -->", "散文", True),
    ("no marker", "128 MB", "128 MB", False),
    # **マーカーを説明している行は、マーカーではない。** 誤認すると、マーカーについて
    # 書いただけで「不当なマーカー」として落ちる（うるさい側の不具合）。
    (
        "documents the marker in a code span",
        "Use `<!-- allow:number-parity -->` when one-sided.\n\nThe cap is 50 GB.",
        "片側だけの数量には `<!-- allow:number-parity -->` を使う。\n\n上限は 50 GB。",
        False,
    ),
]


def selftest() -> int:
    bad = []
    for label, en, ja, want in MARKER_CASES:
        got = unjustified_allow_markers(en, ja)
        if got != want:
            print(
                f"selftest FAIL allow-marker {label}: expected {want} got {got}",
                file=sys.stderr,
            )
            bad.append((label, want))
    for known, has_diff, want in BASELINE_CASES:
        got = baseline_verdict(known, has_diff)
        if got != want:
            print(
                f"selftest FAIL baseline_verdict(known={known}, has_diff={has_diff}): "
                f"expected {want!r} got {got!r}",
                file=sys.stderr,
            )
            bad.append((known, has_diff))
    for en, ja, want in CASES:
        only_en, only_ja = compare(en, ja)
        got = bool(only_en or only_ja)
        if got != want:
            bad.append((en, ja, want, only_en, only_ja))
    for en, ja, want, oe, oj in bad:
        print(
            f"selftest FAIL (expected diff={want}): EN={en!r} JA={ja!r} "
            f"-> only_en={[k for k, _ in oe]} only_ja={[k for k, _ in oj]}",
            file=sys.stderr,
        )
    if bad:
        return 1
    print(
        f"selftest: {len(CASES) + len(BASELINE_CASES) + len(MARKER_CASES)} "
        "case(s) passed"
    )
    return 0


DEC = {"KB": "K", "MB": "M", "GB": "G", "TB": "T", "PB": "P"}
BIN = {"KiB": "K", "MiB": "M", "GiB": "G", "TiB": "T", "PiB": "P"}


def report_unit_collisions() -> int:
    """同一文書で、同じ数字・同じ桁を 10 進接頭辞と 2 進接頭辞の両方で書いている箇所を出す。

    **これは gate ではなく診断。** ``128 MB``（統合目標の概数）と ``128 MiB``
    （``fs.s3a.multipart.size`` の実値）のように、**同じ数字で別の量**を指す共存は正当で、
    落とすと直せない警告になる。落とさずに一覧を出す。

    単位の不一致は値の不一致より見つけにくい。**数字が一致しているので、目視でも
    grep でも一致して見える。** 桁ごとに接頭辞の系統を突き合わせるとだけ現れる。
    """
    total = 0
    for f in tracked():
        p = ROOT / f
        if not p.exists() or any(part in SKIP for part in Path(f).parts):
            continue
        buckets: dict[tuple[str, str], set[str]] = {}
        for key in quantities(p.read_text(encoding="utf-8", errors="replace")):
            num, unit = key.split(" ", 1)
            step = DEC.get(unit) or BIN.get(unit)
            if step:
                buckets.setdefault((num, step), set()).add(unit)
        for (num, _step), units in sorted(buckets.items()):
            if any(u in DEC for u in units) and any(u in BIN for u in units):
                print(f"  {f}: {num} written as {sorted(units)}")
                total += 1
    print(
        f"\n{total} same-number/different-prefix collision(s). Not a failure: the same "
        "digits can legitimately denote different quantities (a rounded target vs a "
        "configured byte value). Where a comparison depends on it, state bytes."
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if "--report-unit-collisions" in sys.argv:
        return report_unit_collisions()

    found = pairs()
    new_total = 0
    new_pairs = 0
    deferred_total = 0
    deferred_pairs = 0
    stale_baseline = []
    inert_markers: list[tuple[str, str]] = []

    for en, ja in found:
        en_text = (ROOT / en).read_text(encoding="utf-8")
        ja_text = (ROOT / ja).read_text(encoding="utf-8")
        only_en, only_ja = compare(en_text, ja_text)
        if unjustified_allow_markers(en_text, ja_text):
            inert_markers.append((en, ja))
        verdict = baseline_verdict(
            en in KNOWN_DIVERGENT_PAIRS, bool(only_en or only_ja)
        )

        if verdict == "stale":
            stale_baseline.append(en)
            continue
        if verdict == "clean":
            continue
        if verdict == "deferred":
            deferred_pairs += 1
            deferred_total += len(only_en) + len(only_ja)
            continue

        new_pairs += 1
        print(f"\n{en}\n{ja}")
        for key, lines in only_en:
            print(f"  EN only  {key:<12} ({', '.join(f'L{n}' for n in lines)})")
        for key, lines in only_ja:
            print(f"  JA only  {key:<12} ({', '.join(f'L{n}' for n in lines)})")
        new_total += len(only_en) + len(only_ja)

    if deferred_pairs:
        print(
            f"\ndeferred: {deferred_total} mismatch(es) across {deferred_pairs} "
            "pair(s) listed in KNOWN_DIVERGENT_PAIRS (whole-document divergence, "
            "tracked as translation catch-up rather than as numbers)"
        )

    if inert_markers:
        print(
            "\nThese pairs carry <!-- allow:number-parity --> markers that suppress "
            "nothing: honouring them and ignoring them produce the same report. A "
            "marker that suppresses nothing still hides whatever drift lands on that "
            "line later. Delete them:",
            file=sys.stderr,
        )
        for en, ja in inert_markers:
            print(f"  {en} / {ja}", file=sys.stderr)
        return 1

    if stale_baseline:
        print(
            "\nKNOWN_DIVERGENT_PAIRS is out of date. These pairs now agree, so "
            "their entries no longer defer anything — they only hide future drift. "
            "Delete them:",
            file=sys.stderr,
        )
        for p in stale_baseline:
            print(f"  {p}", file=sys.stderr)
        return 1

    if new_total:
        print(
            f"\n{new_total} quantity mismatch(es) across {new_pairs} of "
            f"{len(found)} EN/JA pair(s).\n"
            "Each is one of three things: a stale number on one side, the same "
            "quantity written in two different units, or two different quantities "
            "presented as one. Fix the document, or mark the line with "
            "<!-- allow:number-parity --> when the number genuinely belongs to "
            "one language only.",
            file=sys.stderr,
        )
        return 1

    checked = len(found) - deferred_pairs
    print(
        f"number parity: {checked} EN/JA pair(s) agree on every unit-bearing "
        f"quantity ({deferred_pairs} deferred)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
