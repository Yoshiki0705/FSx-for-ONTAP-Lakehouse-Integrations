#!/usr/bin/env python3
"""日本語の節見出しが体言止め（名詞句）であることを検査する。

対象は ``##`` 以下の節見出しのみ。H1 は文書タイトル（別規約で「1 行の主張文」）
なので対象外。frontmatter に ``title:`` を持つ媒体（blog/）でも、本文中の ``#``
はすべてコードフェンス内のシェルコメントであることを確認済みなので、H2 起点で
足りる。

対象外の扱い:
  - コードフェンスの内側（``#`` はシェルのコメントであって見出しではない）
  - かなを含まない見出し（英語見出しは ``Deleting a volume`` で正しい）
  - ``<!-- allow:heading-style -->`` を付けた見出し（叙述・助言・抱負）

使い方:
  python3 scripts/check-heading-style.py --selftest   # 検査が落ちる能力の確認
  python3 scripts/check-heading-style.py              # 本検査
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 走査範囲は git の追跡ファイル。`blog/` のように gitignore された下書きを拾うと、
# ローカルだけが落ちて CI は通る（あるいはその逆の）状態になり、何を見たのかが
# 結果から読めなくなる。git が使えない環境では下の SKIP 付き rglob に落ちる。
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

HEADING = re.compile(r"^(#{2,6})\s+(.*?)\s*$")
FENCE = re.compile(r"^\s*(?:```|~~~)")
ALLOW = re.compile(r"<!--\s*allow:heading-style\s*-->")
CODE_SPAN = re.compile(r"`+[^`]*`+")
JAPANESE = re.compile(r"[ぁ-んァ-ヶ一-龠]")


def effective(line: str) -> str:
    """コードスパンを落とした行を返す。マーカーの有無はこの結果で判定する。

    **マーカーを説明している行が、マーカーとして数えられてはいけない。** ここでの害は
    静かな側に出る。構文例をバッククォートで囲んだ見出しは、素朴な検索ではマーカー付きと
    区別できず、**その見出しの違反が免除される。説明している行が自分を検査対象から外す。**
    """
    return CODE_SPAN.sub("", line)

# 文字クラスはう段だけ。動詞の終止形はう段で終わる。
#
#   `れ` を入れてはいけない。え段であって終止形にはならず、単独の `れ` は連用形の
#   名詞化（流れ / 崩れ / 遅れ / ずれ）。入れると閉じられない名詞クラスを誤検出し、
#   許可リストでは対処できない。
#
#   `ない` は個別に列挙する。`い$` で一括にしてはいけない。平叙の否定（…できない）は
#   文だが、`問い` `扱い` は名詞である。列挙を省くと否定の述語見出しを無言で通す。
VERBAL = re.compile(
    r"(?:ます|ません|ました|でした|です|ください|でしょうか|のか|か|ない"
    r"|[うくぐすずつぬふぶむる])$"
)

# 名詞の許可リストは置かない。`れ` をクラスから外した時点で、許可リストの全語が
# そもそも VERBAL に一致しなくなる。発火しない許可リストは、提供していない保証を
# 表明することになる。効いているのは「`ない` をリテラルにした」点だけ。


def is_violation(heading_text: str) -> bool:
    """見出し本文が体言止めでない（＝違反）か。**判定はこの 1 か所だけ。**

    ``violations`` と ``inert_allows`` の両方がここを呼ぶ。**同じ規則を 2 か所に書くと
    片方が狭くなり、しかもその非対称は「意図的」として説明できてしまう。** 実際に起きた
    ずれ: 本体はコードスパンを落として判定し、不活性検査は原文で判定していた。結果、
    あるマーカー付きの見出しが「必要」かつ「不活性」になり、**消しても残しても落ちる**
    状態になった。

    コードスパンを落とすのは、識別子やパス（``volume delete`` など）が末尾に来ると
    その綴りで述語判定が揺れるため。
    """
    h = ALLOW.sub("", effective(heading_text)).strip()
    if not JAPANESE.search(h):
        return False
    return bool(VERBAL.search(h))


def inert_allows(text: str) -> list[tuple[int, str]]:
    """許可マーカーが何も抑制していない行を返す。

    **マーカーは主張である**（この見出しは意図的に叙述だ、という主張）。見出しを書き換えて
    抑制対象が無くなれば主張も無効になるが、マーカーは残る。**残ったマーカーは、その行に
    将来入り込む違反を黙って通す。** baseline の一覧と同じで、**縮むしかない性質が無い
    抑制は、抑制ではなく永久の穴になる。**

    失われても実行結果は静かに正常に見える種類の不具合なので、selftest と mutation で
    押さえる。
    """
    found: list[tuple[int, str]] = []
    in_fence = False
    for n, line in enumerate(text.split("\n"), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or not ALLOW.search(effective(line)):
            continue
        # マーカーを先に落とさない。**落とすと ``is_violation`` 側の除去と二重になり、
        # どちらか一方を壊す変異が無害化する。** 実測: 二重にしていた間、
        # 「``is_violation`` がマーカーを落とさない」変異と「ここで原文を使う」変異が
        # **どちらも全テストを通過していた**（個別には無害、両方外すと壊れる）。
        # 除去は ``is_violation`` の 1 か所だけにする。
        m = HEADING.match(line.rstrip())
        if not m:
            continue  # 見出しでない行のマーカーは、この検査の対象ではない
        # **判定は ``is_violation`` に委ねる。** ここに独自の判定を書くと、監査本体と
        # 幅がずれる。実際にずれていた: 本体はコードスパンを落として判定し、ここは
        # 原文で判定していたため、``## 実行する `--flag``` にマーカーを付けた行が
        # **「マーカーが必要」かつ「マーカーは不活性」**の両方になり、消しても残しても
        # 落ちる状態になっていた。同じ規則を 2 か所に書くと、片方が狭くなる。
        if not is_violation(m.group(2).strip()):
            found.append((n, m.group(2).strip()))
    return found


def violations(text: str) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    in_fence = False
    for n, line in enumerate(text.split("\n"), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or ALLOW.search(effective(line)):
            continue
        m = HEADING.match(line)
        if not m:
            continue
        raw = m.group(2).strip()
        # 表示は原文のまま。**加工した文字列を出すと、直す対象の行をファイル内で
        # 検索できない。** 判定側の加工は ``is_violation`` の中にある。
        if is_violation(raw):
            found.append((n, m.group(1), raw))
    return found


# 両方向を証明する。落ちない検査は、検査が無いのと区別できない。
CASES = [
    ("## 自分の環境で確かめる", True),
    ("## 検証を自動化する", True),
    ("## なぜこの区分が必要か", True),
    ("## どう分けるか", True),
    ("## 読み取りがあります", True),
    ("## 面に分かれました", True),
    ("## 既定は「同一」です", True),
    ("## アクセスは成立する", True),
    ("## AWS 側からしか消せない", True),
    ("## この経路を見ていない", True),
    ("## 自環境での確認手順", False),
    ("## 必要な理由", False),
    ("## 読み取りの存在", False),
    ("## 解除の不可", False),
    ("## 追加する流れ", False),
    ("## 最小権限の崩れ", False),
    ("## 実測の遅れ", False),
    ("## 扱う問い", False),
    ("## 権限の扱い", False),
    ("## よくある誤解", False),
    ("## 判断フロー", False),
    ("## ログの保存先", False),
    ("## リスクの一覧", False),
    ("## Deleting a volume", False),
    ("## How to choose", False),
    ("# タイトルは主張文で書く", False),
    ("## 15:29 気付く <!-- allow:heading-style -->", False),
]


# 許可マーカーが効いているか（True = 何も抑制しておらず、消すべき）。
# **マーカー自体が違反を隠せる位置にあるので、ここを試さないと「マーカーを付ければ通る」
# だけの逃げ道が永久に残る。**
ALLOW_CASES = [
    # 外すと違反になる = マーカーは働いている。
    ("## 15:29 気付く <!-- allow:heading-style -->", False),
    ("## アクセスは成立する <!-- allow:heading-style -->", False),
    # 外しても違反にならない = マーカーは何も抑制していない。
    ("## 自環境での確認手順 <!-- allow:heading-style -->", True),
    ("## よくある誤解 <!-- allow:heading-style -->", True),
    # 英語見出しはそもそも対象外なので、マーカーは不要。
    ("## Deleting a volume <!-- allow:heading-style -->", True),
    # 見出しでない行のマーカーは対象外（本文の注記など）。
    ("この行は見出しではない <!-- allow:heading-style -->", False),
    # **マーカーを説明している見出しは、マーカー付きではない。** コードスパン内の構文例を
    # 本物と誤認すると、その見出しの違反が免除される（静かな側の不具合）。
    ("## `<!-- allow:heading-style -->` を付けてください", False),
    # 述語のあとにコードスパンが来る形。**判定を 2 か所に書いていたとき、ここが
    # 「不活性かつ必要」になっていた。** 下の不変条件が組み合わせを押さえる。
    ("## 実行する `--flag` <!-- allow:heading-style -->", False),
    # **フェンス内のマーカーは指令ではないので、不活性としても報告しない。**
    # ここが空だった間、``inert_allows`` からフェンス判定を外す変異が全テストを
    # 通過していた。表が 1 行だけの文字列ばかりだと、複数行の入力が検査されない。
    ("```md\n## 気付く <!-- allow:heading-style -->\n```\n", False),
    ("```\n## 確認手順 <!-- allow:heading-style -->\n```\n", False),
]

# 自己言及の分離。**説明が自分を検査対象から外す形**を両方向で固定する。
SELF_REFERENCE_CASES = [
    # (入力, 違反として報告すべきか)
    # コードスパン内の構文例は抑制しない → 述語なので報告される。
    ("## `<!-- allow:heading-style -->` を付けてください", True),
    ("## `allow:heading-style` を使う", True),
    # フェンス外の本物のマーカーは抑制する。
    ("## 気付く <!-- allow:heading-style -->", False),
    # コードスパンは判定から落ちるが、外側の日本語は判定に残る。
    ("## `volume delete` を実行する", True),
    ("## `volume delete` の手順", False),
]


def selftest() -> int:
    bad = [(c, want) for c, want in CASES if bool(violations(c)) != want]
    if violations("```bash\n# コピー元で実行しておく\n```\n"):
        bad.append(("fence", False))
    for c, want in ALLOW_CASES:
        if bool(inert_allows(c)) != want:
            bad.append((f"[inert] {c}", want))
    for c, want in SELF_REFERENCE_CASES:
        if bool(violations(c)) != want:
            bad.append((f"[self-ref] {c}", want))
    # **不変条件。個別の期待値ではなく関係を固定する。**
    # 「不活性」と「外すと違反」は**ちょうど一方**が成り立たなければならない。両方でも
    # どちらでもなく、排他的択一である。個別ケースの期待値を並べるだけでは、
    # **2 つの検査が別々に正しく、組み合わせだけが壊れている**状態を見逃す。
    #
    # 2 方向とも実害がある。
    #   both    = 消しても残しても落ちる行（修正不能）
    #   neither = 外しても違反にならないのに不活性と報告されないマーカー（永久に残る）
    # 最初は both だけを検査していた。**片方向だけの不変条件は、不変条件の形をした
    # 部分検査である。** 234 の見出し形で排他的択一が成立することを確認したうえで、
    # 構造がそうなっている（両者が同じ ``is_violation`` から導かれる）ことに依拠する。
    for c, _ in ALLOW_CASES:
        if not ALLOW.search(effective(c)):
            continue
        if not HEADING.match(ALLOW.sub("", c).rstrip()):
            continue  # 見出しでない行は両検査の対象外
        stripped = ALLOW.sub("", c).rstrip()
        if bool(inert_allows(c)) == bool(violations(stripped)):
            state = "両方成立（修正不能）" if inert_allows(c) else "どちらも不成立（無用なマーカーが残る）"
            bad.append((f"[invariant] {state}: {c}", False))
    for c, want in bad:
        print(f"selftest FAIL (expected flag={want}): {c}", file=sys.stderr)
    if bad:
        return 1
    print(
        f"selftest: {len(CASES) + len(ALLOW_CASES) + len(SELF_REFERENCE_CASES) + 1} "
        "case(s) passed"
    )
    return 0


def targets() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "--", "*.md"],
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
        paths = [ROOT / n for n in out.split("\0") if n]
        if paths:
            return sorted(paths)
    except (OSError, subprocess.CalledProcessError):
        pass
    return sorted(
        p for p in ROOT.rglob("*.md") if not any(part in SKIP for part in p.parts)
    )


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    total = 0
    inert = 0
    for p in targets():
        if any(part in SKIP for part in p.parts):
            continue
        text = p.read_text(encoding="utf-8")
        stale = inert_allows(text)
        if stale:
            print(f"\n{p.relative_to(ROOT)}")
            for n, h in stale:
                print(f"  L{n:>4} 許可マーカーが何も抑制していません: {h}")
            inert += len(stale)
        hits = violations(text)
        if not hits:
            continue
        print(f"\n{p.relative_to(ROOT)}")
        for n, h, t in hits:
            print(f"  L{n:>4} {h} {t}")
        total += len(hits)

    if inert:
        print(
            f"\n{inert} 件の許可マーカーが何も抑制していません。見出しを直したあとに"
            "残ったものです。**削除してください。** 残すと、その行に将来入り込む違反を"
            "黙って通します（抑制は縮むしかない状態に保つ）。",
            file=sys.stderr,
        )
        return 1
    if total:
        print(
            f"\n{total} 件が体言止めではありません。"
            "接尾語で断定を保って名詞化してください。",
            file=sys.stderr,
        )
        return 1
    print("heading style: all Japanese section headings are noun phrases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
