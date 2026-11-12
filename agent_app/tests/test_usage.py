"""How a plan was used and where it came from (definition 15)."""

from agent_app.usage import lineage
from test_runs import run_once, scenario


def test_a_version_counts_the_ais_runs_and_its_line_crosses_datasets(
    tmp_path, monkeypatch
):
    # Astra 2026-10-17 P06: a version "used 7 times" counted 6 person's fixes; a plan copied to
    # another dataset did not say where it came from.
    async def body(app, client, dataset, ids):
        first = await run_once(client, app, dataset)
        a = ids["a.png"]
        result = (await client.get(f"/v1/runs/{first['id']}/results")).json()["results"]
        made = next(r["result_id"] for r in result if r["image_id"] == a)
        fixed = await client.post(
            f"/v1/datasets/{dataset}/images/{a}/fixes",
            json={"from_result_id": made, "annotations": []},
        )
        assert fixed.status_code == 201, fixed.text
        versions = f"/v1/datasets/{dataset}/instructions"
        version = (await client.get(versions)).json()["instructions"][0]
        assert (version["runs"], version["trials"]) == (1, 0)
        used = version["usage"]
        assert {k: used[k] for k in ("images", "succeeded", "failed")} == {
            "images": 2,
            "succeeded": 1,
            "failed": 1,
        }
        assert (used["adopted"], used["fixed"]) == (0, 1)

        copy = (
            await client.post(
                f"/v1/datasets/{dataset}/copy", json={"name": "写し", "purpose": "円"}
            )
        ).json()["id"]
        assert (await client.get(f"/v1/datasets/{copy}/instructions")).json()[
            "instructions"
        ] == []
        draft = (await client.get(f"/v1/datasets/{copy}/drafts/instruction")).json()
        came = {"kind": "version", "dataset_id": dataset, "revision": 1}
        assert draft["from"] == came
        await run_once(client, app, copy)
        made_there = (await client.get(f"/v1/datasets/{copy}/instructions")).json()
        assert made_there["instructions"][0]["from"] == came
        line = lineage(app.state.db, dataset, 1)
        assert [(d["dataset_id"], d["revision"]) for d in line["derived"]] == [
            (copy, 1)
        ]
        assert line["derived_total"]["adopted"] == 1
        assert lineage(app.state.db, copy, 1)["based_on"] == [
            {"dataset_id": dataset, "name": "円", "revision": 1}
        ]

    scenario(tmp_path, monkeypatch, body)
