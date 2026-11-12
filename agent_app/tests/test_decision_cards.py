"""What deciding needs, made by the server for every screen (definition 16)."""

from agent_app.shared_notes import FIRST, RULES
from test_runs import run_once, save_version, scenario

LUNA = {"model": "gpt-6-luna", "effort": "medium"}
SONNET = {"model": "claude-sonnet-5-5", "effort": "medium"}


async def card_of(client, dataset, **args):
    found = await client.post(
        f"/v1/datasets/{dataset}/proposals/preview",
        json={
            "tool": "run_start",
            "args": {"budget_per_image_usd": "1", **args},
            "title": "流す",
            "reason": "確かめ",
        },
    )
    assert found.status_code == 200, found.text
    return found.json()["preview"]["card"]


def test_a_run_card_says_what_it_fixes_what_happens_and_what_it_stands_on(
    tmp_path, monkeypatch
):
    # User 2026-10-17: a decision needs its information where it is made; a trial is light,
    # the run of the rest heavy, and what is missing is shown as missing.
    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        first = await card_of(client, dataset, trial=True, image_ids=[a], revision=1)
        assert first["weight"] == "light" and first["happens"]["used_after"] == [a]
        assert {"first_run", "not_tried"} <= set(first["blanks"])
        await run_once(client, app, dataset, trial=True, image_ids=[a], revision=1)
        rest = await card_of(client, dataset, revision=1, **LUNA)
        assert (rest["decision"], rest["weight"]) == ("run", "heavy")
        assert [t["image_id"] for t in rest["grounds"]["trials"]] == [a]
        assert (rest["happens"]["redo"], rest["happens"]["replaces"]) == (1, [a])
        assert rest["grounds"]["way"]["trials"] == 1
        assert not {"first_run", "not_tried"} & set(rest["blanks"])
        # A plan started from another dataset stands on that version and its use.
        other = (
            await client.post(
                "/v1/datasets",
                json={"name": "別", "purpose": "円", "image_ids": [a]},
            )
        ).json()["id"]
        started = await client.post(
            f"/v1/datasets/{other}/plan/start",
            json={"kind": "other", "dataset_id": dataset, "revision": 1},
        )
        assert started.status_code == 200, started.text
        card = await card_of(
            client, other, draft_write_id=started.json()["write_id"], **LUNA
        )
        line = card["grounds"]["line"]
        assert line["origin"] == {
            "kind": "version",
            "dataset_id": dataset,
            "revision": 1,
            "name": "円",
        }
        assert line["origin_usage"]["trials"] == 1 and card["grounds"]["way"] is None
        # Nothing ran here yet: the cost is the same plan's by the same way in the datasets
        # that ran it (user 2026-10-17; definition 84).
        assert [d["dataset_id"] for d in card["happens"]["estimate_from"]] == [dataset]
        assert card["happens"]["estimate_usd"] and "no_estimate" not in card["blanks"]

    scenario(tmp_path, monkeypatch, body)


def test_a_plan_starts_from_blank_or_another_datasets_version(tmp_path, monkeypatch):
    # Definition 16.2: copying and going back are one operation.
    async def body(app, client, dataset, ids):
        other = (
            await client.post(
                "/v1/datasets",
                json={"name": "四角", "purpose": "四角", "image_ids": [ids["a.png"]]},
            )
        ).json()["id"]
        squares = [{"name": "square", "shape": "bbox", "attributes": []}]
        save_version(
            app.state.db, other, {"text": "四角を囲む", "label_definitions": squares}
        )
        base = f"/v1/datasets/{dataset}"
        await client.post(f"{base}/plan/start", json={"kind": "blank"})
        blank = (await client.get(f"{base}/drafts/instruction")).json()
        assert blank["from"] == {"kind": "blank"}
        await client.post(
            f"{base}/plan/start",
            json={"kind": "other", "dataset_id": other, "revision": 1},
        )
        draft = (await client.get(f"{base}/drafts/instruction")).json()
        assert draft["from"] == {"kind": "version", "dataset_id": other, "revision": 1}
        assert [d["name"] for d in draft["label_definitions"]] == ["square"]
        assert draft["references"] == []

    scenario(tmp_path, monkeypatch, body)


def test_a_worker_is_not_fixed_to_one_language():
    # 2026-11-05: a plan in English got the AI's messages in Japanese, and an empty database's
    # shared notes showed Japanese on an English person's plan screen.
    assert "Japanese" not in RULES
    assert "the language of instruction_text" in RULES
    assert FIRST.isascii()


def test_a_run_adds_the_shared_notes_of_the_version_it_holds(tmp_path, monkeypatch):
    # User 2026-10-17: the advice to every worker AI lived in the settings without versions; a
    # version run again after it changed got other words, and no card said so (18.15).
    async def body(app, client, dataset, ids):
        first = (await client.get("/v1/shared-notes")).json()["latest"]
        ran = await run_once(client, app, dataset, image_ids=[ids["a.png"]])
        second = (
            await client.put(
                "/v1/shared-notes", json={"text": "全体を見てから細部を見る。"}
            )
        ).json()
        assert (first["revision"], second["revision"]) == (1, 2)
        prompt = app.state.db.one(
            "SELECT worker_prompt FROM runs WHERE id=?", (ran["id"],)
        )[0]
        assert first["text"] in prompt and second["text"] not in prompt
        card = await card_of(client, dataset, image_ids=[ids["a.png"]], revision=1)
        assert card["fixes"]["shared_revision"] == 2
        assert card["fixes"]["changes"]["shared"] == [1, 2]

    scenario(tmp_path, monkeypatch, body)


def test_a_decision_is_checked_as_its_run_will_be(tmp_path, monkeypatch):
    # Review 2026-10-28 (C#9): a worker named the model by its display name; the decision was
    # made, and failed only once a person decided it. A limit of 0 was taken the same way.
    async def body(app, client, dataset, ids):
        async def made(**args):
            return await client.post(
                f"/v1/datasets/{dataset}/proposals/preview",
                json={
                    "tool": "run_start",
                    "args": args,
                    "title": "流す",
                    "reason": "r",
                },
            )

        named = await made(model="GPT-6-Luna")
        assert (named.status_code, named.json()["error"]["code"]) == (
            422,
            "invalid_model",
        )
        assert "gpt-6-luna" in named.json()["error"]["details"]["models"]
        free = await made(model="gpt-6-luna", budget_per_image_usd="0")
        assert (free.status_code, free.json()["error"]["code"]) == (
            422,
            "invalid_input",
        )
        assert (await made(**SONNET)).status_code == 200

    scenario(tmp_path, monkeypatch, body)
