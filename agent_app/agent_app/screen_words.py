"""The screen's words for the workers' rules, in one place (issue #3 U-14: the list was copied into
every prompt, and the copies said different things). Each prompt puts words() where it says how
to speak; the words are those of the screen's dictionary and definition 16.3. The dictionary
itself (dictionary()) names what a worker reads by the screen's words (definition 71: the
settings).
"""

import json
from functools import cache

from .config import APP

# The screen's dictionary (ui/src/i18n), in the zip too (tools/handout/build.py).
DICTIONARY = APP / "ui/src/i18n"

# (the screen's word, in English, what it is, the words never used for it)
WORDS = (
    ("データセット", "dataset", None, None),
    (
        "計画書",
        "plan",
        (
            "what 計画 makes and AI でアノテーションする follows: one saved is 第n版 / version n"
            " (今の計画書 / the plan now is the latest one), the one being written is 下書き /"
            " draft; say which (2026-10-29: a draft was called 今の計画書)"
        ),
        "実施案",
    ),
    (
        "決定",
        "decision",
        (
            "a press that changes the data; one a worker made ready waits for the person"
            " as 決定待ち / waiting decision"
        ),
        "提案",
    ),
    ("AI でアノテーションする", "annotate with AI", "a run", "流す or 依頼"),
    ("見本を作る", "make samples", "a trial: the plan on a few images", "試し"),
    ("アノテーション済み", "annotated", None, None),
    ("アノテーションの記録", "annotation record", "one run or a person's fix", "依頼"),
    ("学習に使う・使わない", "use or not use for training", None, "採用"),
    (
        "参照",
        "reference",
        "a result chosen as the plan's example of the way of annotating",
        "参考例 (2026-10-29: one question said 参考例, another 参照)",
    ),
    ("頼む", "ask", "only a person asking a worker", None),
    ("伝える", "pass on", "a request handed to a worker", "回す"),
    ("あなたの番", "your turn", "what waits for the person", None),
    (
        "困りごと",
        "trouble",
        "what failed or went out of date, for the person to see; one is 'a problem'",
        "a trouble",
    ),
)
# How numbers and refusals are said, the same for every worker (the reception's and steward's
# tests 2026-10-29: "3 existing plans" with two of them to choose, a cost "twice this model's" of
# no model named, a folder not there said as "may not be there").
SAYING = (
    "A number of things you say there are to choose from is the number of your options; when"
    " they do not all fit, say the rest are on the right. A cost you compare or estimate names"
    " its model. What the server refused, say as it said it (a folder not found is not found),"
    ' never as a maybe. In English, a name goes in quotes (#12 "Animals"), never 「」.'
)
# The language a worker answers in, the same for every worker (definition 75; 2026-10-29: asked in
# English on a Japanese screen, the steward answered in Japanese, the screen's).
LANGUAGE = (
    "in the language the person wrote in (when their words show none, as a number alone, their"
    " screen's: context.language)"
)
# Times as the screen says them (definition 74; 2026-10-29: one answer said a record's time in
# UTC, another in the person's).
TIMES = (
    "Times you read end in Z (UTC): say them in the person's time, as context.now (their time"
    " now, with its offset from UTC) shows, as 10/29 18:20, with no zone named."
)
WORKERS = (
    "The workers (definition 35.1): 受付 / Guide (reception, the library's) and 担当 / Steward"
    " (steward, a dataset's); a worker is called by its name alone, no 係. A dataset's screens,"
    " chosen at the top right (画面 / Screen): 計画 / Plan (instruction), AI でアノテーションする /"
    " Annotate with AI and 学習に使う・外す / Use for training or not (production); the library's:"
    " 取り込む / Take in, 削除する / Delete and 書き出す / Write out; no numbers, never 実施 or Apply."
)


def words():
    """How to name things, as one sentence of a prompt."""
    said = []
    for word, english, means, never in WORDS:
        notes = "; ".join(n for n in (means, f"never {never}" if never else None) if n)
        said.append(f"{word} / {english}" + (f" ({notes})" if notes else ""))
    return f"Use the screen's words: {', '.join(said)}. {WORKERS} {TIMES} {SAYING}"


@cache
def dictionary():
    """The screen's words by key, in each of its languages."""
    return {
        lang: json.loads((DICTIONARY / f"{lang}.json").read_text(encoding="utf-8"))
        for lang in ("ja", "en")
    }


def screen(key):
    """A key's words on the screen, in each language."""
    return {lang: words.get(key) for lang, words in dictionary().items()}
