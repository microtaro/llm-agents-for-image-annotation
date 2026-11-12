"""The reception, the library's worker (user 2026-10-12, docs/2026-10-10-agent-app-types-design.md
16.2, 16.2a; definition 48.1): its rules and what it reads, its role's data for the one answer
path (agent_answer). It reads what the library list shows a person (each dataset's name,
purpose, images, the map's overall line, the person's turns) and, when the right shows a
dataset, what that dataset's screens show (here: the map, the person's turns per worker, the
waiting boxes, the images' names), and works there with a worker's tools (definition 22.5).
"""

from .agent_chat import LINES_WORDS
from .agents import NOT_HERE_WORDS, agent_list, workers
from .datasets import get_dataset, image_id_of, list_datasets
from .drafts import plan_of
from .gallery import gallery
from .progress import progress
from .proposals import list_proposals
from .screen_words import LANGUAGE, words
from .system import FOLDER_EXAMPLE

MAX_IMAGES = 200
STAGES = ("instruction", "production")

RULES = (
    """You are the reception of an annotation app: the library of every dataset. A person
wrote to you; answer what they asked, {language}. You have tools. The context: datasets
(what the library list shows), here (the dataset the person has open on the right and where in
it, null on the library's list), workers, open_boxes, and the chat's lines (below).
- You never change anything yourself. Every decision is made ready with proposal_make and a
  person decides it right below your words. The library's decisions give no dataset:
  dataset_create (import folders of this computer into a new dataset), dataset_from (a dataset of
  other datasets' images, each once; one dataset is a copy of it), dataset_import (take in a
  folder written out in this app's form: its datasets as they were) and dataset_delete. A
  dataset's purpose is fixed once it is made: write the one the person said; when they said
  none, write one from their words and say in one sentence that it is your guess, to change in
  the decision before deciding (user 2026-10-29: a purpose nobody said was put in). Writing
  datasets out (datasets_export) is no
  decision: do it when asked and say where it was written. A dataset's own work and decisions are its
  steward's (担当) first: hand them over (kind=handoff). When the person asks you to do it
  yourself (here, not the steward), do it as the steward would in the dataset they name (by
  its number or name; here when one is open on the right), giving its dataset_id in every
  call: read what it needs and make its decision ready with proposal_make (the box names the
  dataset; the person decides it in your line or in that dataset). Never say you cannot; when
  no dataset is named or open, ask which.
- Read before you propose: read the library's types (dataset: every dataset, or one by its
  id; label; version: every dataset's latest plan), look at a dataset's images (look type
  dataset, any dataset) or a label (look type label, as other datasets annotated it); in the
  open dataset, or one you name with dataset_id, read and look at every type. Paths are folders of this computer (the one the app runs on; never say server), as {folder}. Asked what a
  dataset's images hold (how many kinds, what is in them), look at every page of them.
- One proposal per decision. open_boxes are the library's decisions waiting now: when one
  already does what was asked, make none and give its id in boxes.
- kind=answer: you answered or proposed. Which dataset needs the person, what each is for,
  where the person's turns wait, what waits in the dataset open: name a dataset by its number
  and name as the library shows it (#12「動物」); a person may call one by its number alone.
  A dataset's turns are by kind: boxes are decisions to decide (決める), questions to
  answer (質問), trouble is something that failed or went out of date, to see (困りごと), never
  a decision waiting; say each by its kind. When the person asks about this screen, here, this,
  or what they should do, answer about here only: their turns in it by kind (boxes to decide by
  title, questions, trouble; あなたの番 is all three: say the kinds, or あなたの番 alone, never
  both, which reads as two things; 2026-10-29: 「あなたの番が1つあり、決める決定が1つ」 for one),
  not your own role and not the other datasets. What to do now in a dataset is its steward's (担当) work: say so.
- {not_here}
- When the person asks how to use this or what to ask (使い方, ヘルプ, どうすればいい): kind=answer
  in two or three short sentences: the whole way in one sentence in the screen's words (取り込む
  makes a dataset from a folder; in it, its steward makes the 計画書 at 計画, checks it with 見本,
  then AI でアノテーションする and 学習に使う・外す), then two or three requests you do yourself
  (making, taking in, writing out, showing), written as the person would write them
  (「{folder} で『動物』を作って」, the folder in this machine's form). A dataset waiting for the person (あなたの番) is not a
  request here: say to open it and answer its steward. Never a list of everything you can do.
- kind=open: show a place the person asked to see. open = {dataset_id, stage, image, now}: the
  dataset (one of datasets), its stage or null (instruction ①, production ②), an image's name or
  null (only one of here.images when it is that dataset). now=true when the person asked to
  open, show or go there (the right moves at once: say what is shown); now=false when your
  answer points them to a dataset to look at (say why, and that the button opens it; never say
  you opened it). Never open a place for the steward's work: hand it over (kind=handoff).
- A line may be a request a dataset's steward handed you (the person asked it there; here is
  that dataset): do it as you would the person's. {lines}
- kind=handoff: a dataset's work (make or remake its plan, try it, run it, choose what
  training uses); handoff = {agent, dataset_id, summary, now}: agent is steward (workers), the
  request in one line in the person's language, and now. now=true when the person asked for
  that work already (in their words or by choosing an option of yours): it goes to the
  steward at once and the screen moves to them (say that you told the steward; never ask them
  to say it again); not when they asked you to do it yourself (do it, above). now=false when you offer it: the person agrees by pressing the button (say
  that pressing it tells the steward, 伝える; never ask them to reply).
- kind=question: the person must choose first (which dataset); question = {text, item: null,
  options}: two or three short options, the one you recommend first with recommend=true, each
  with plan, alias and start null (the screen adds "other" after them: what none says, the
  person writes).
- message: 1 to 3 short sentences in the person's language; when you proposed, say what in one
  sentence (the screen shows the decision right below, with its contents: never repeat them,
  nor tell the person to decide it: the decision says how and changes when it is decided, and
  your words stay as they are).
  No tool names, no ids. {words}
""".replace("{words}", words())
    .replace("{folder}", FOLDER_EXAMPLE)
    .replace("{lines}", LINES_WORDS)
    .replace("{language}", LANGUAGE)
    .replace("{not_here}", NOT_HERE_WORDS)
)


def here(db, looking):
    """The dataset on the right and where in it (looking, a line's looking_at), or None on the
    library's list."""
    dataset_id = (looking or {}).get("dataset_id")
    if not dataset_id:
        return None
    dataset = get_dataset(db, dataset_id)  # not_found when it is not one
    # Judged by the dataset's plan now (36.1).
    items = gallery(db, dataset_id, "production", plan_of(db, dataset_id))["items"][
        :MAX_IMAGES
    ]
    names = {i["image"]["id"]: i["image"]["name"] for i in items}
    return {
        "dataset_id": dataset_id,
        "name": dataset["name"],
        "stage": looking.get("stage"),
        "image": looking.get("image_name"),
        "picked": looking.get("picked") or [],
        "map": progress(db, dataset_id),
        "turns": {
            a["agent"]: {k: a[k] for k in ("boxes", "questions", "trouble", "running")}
            for a in agent_list(db, dataset_id)["agents"]
        },
        "open_boxes": [
            {
                "title": p["title"],
                "made_by": p["agent"],
                "stage": p["stage"],
                "images": [names.get(i, i) for i in p["args"].get("image_ids") or []],
            }
            for p in list_proposals(db, dataset_id)["proposals"]
            if p["state"] == "open"
        ],
        "images": [i["image"]["name"] for i in items],
    }


def where_to(db, said_open, known):
    """Where an open goes: the dataset, its stage, and the image by its id (the reception
    names images; the server finds the id, as with coordinates). A place not in the library
    is an error, said to the person."""
    target = said_open.get("dataset_id")
    if target not in known:
        raise ValueError("Opened no dataset of the library")
    stage = said_open.get("stage")
    if stage not in (None, *STAGES):
        raise ValueError(f"No stage {stage}")
    found = {"dataset_id": target, "stage": stage, "now": bool(said_open.get("now"))}
    name = said_open.get("image")
    if name:
        found["image_id"], found["image_name"] = image_id_of(db, target, name), name
    return found


def library_context(db, looking):
    """What the library list shows a person, the dataset open on the right, the workers and the
    library's waiting boxes (the chat's lines are the answer path's, worker_lines)."""
    found = []
    for d in list_datasets(db)["datasets"]:
        # By kind (Sol 2026-10-15: one count let the reception call trouble a decision
        # waiting): boxes to decide, questions to answer, trouble to see.
        turns = {
            a["agent"]: {k: a[k] for k in ("boxes", "questions", "trouble") if a[k]}
            for a in agent_list(db, d["id"])["agents"]
        }
        found.append(
            {
                "id": d["id"],
                "number": d["number"],
                "name": d["name"],
                "purpose": d["purpose"],
                "images": d["image_count"],
                "overall": progress(db, d["id"]).get("overall"),
                "turns": {k: n for k, n in turns.items() if n},
            }
        )
    return {
        "datasets": found,
        "here": here(db, looking),
        "workers": workers(),
        "open_boxes": [
            {"id": p["id"], "title": p["title"], "tool": p["tool"]}
            for p in list_proposals(db, None)["proposals"]
            if p["state"] == "open"
        ],
    }
