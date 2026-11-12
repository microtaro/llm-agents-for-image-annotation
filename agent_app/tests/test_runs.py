"""Runs: each worker writes only its own result, the steps are checked from its MCP traffic,
and the run keeps what the worker was asked (step 2 design 6)."""

import asyncio
import base64
import hashlib
import io
import json
import os
from uuid import uuid4

import httpx
from agent_app.actors import PERSON
from agent_app.app import create_app
from agent_app.codex_execution import inference_prompt
from agent_app.inference import read_usage
from agent_app.instructions import InstructionInput, save_instruction
from agent_app.runs import RunExecution
from PIL import Image

from agent_app import codex_execution
from agent_app import jobs as jobs_module
from agent_app import runs as runs_module

CIRCLE = {"type": "bbox", "xywh": [100, 50, 40, 30]}
USAGE = b'{"type":"thread.started","thread_id":"s"}\n{"type":"turn.completed","usage":{"input_tokens":3000,"cached_input_tokens":0,"output_tokens":100}}\n'
DEFINITIONS = [
    {
        "name": "circle",
        "shape": "bbox",
        "attributes": [{"name": "color", "type": "choice", "choices": ["red", "blue"]}],
    }
]


def fake_inference(app, fail_names=("fail.png",), skip_whole=False, unsearched=()):
    """Do what a real worker does, through the same HTTP routes and MCP envelopes."""

    async def inference(directory, run, result_id, stop, record):
        # The real worker gets this prompt; the run must carry it (found 2026-10-05).
        assert f"result_id: {result_id}" in inference_prompt(run, result_id)
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers={
                "X-Annotation-Run-Id": run["id"],
                "X-Annotation-Result-Id": result_id,
            },
        )

        async def emit(tool, arguments, data=None, response=None, shown=None):
            envelope = {"ok": True, "data": data, "view": None, "reference_views": []}
            content = []
            if response is not None:
                envelope["view"] = json.loads(response.headers["x-annotation-view"])
                content.append(
                    {
                        "type": "image",
                        "mimeType": response.headers["content-type"],
                        "data": shown or base64.b64encode(response.content).decode(),
                    }
                )
            item = {
                "id": str(uuid4()),
                "type": "mcp_tool_call",
                "tool": tool,
                "arguments": arguments,
                "status": "completed",
                "result": {"structured_content": envelope, "content": content},
            }
            await record({"type": "item.completed", "item": item})

        async with client:
            task = (await client.get(f"/v1/results/{result_id}/task")).json()
            await emit("task_get", {"result_id": result_id}, task)
            for ref in task["refs"]:
                shown = await client.post(
                    f"/v1/results/{result_id}/references/{ref['index']}/views", json={}
                )
                assert shown.status_code == 200, shown.text
                frame = json.loads(shown.headers["x-annotation-view"])
                app.state.seen_refs.append((task["image_id"], ref, frame))
            # Asks for more than a run allows; the run's image size caps it.
            crop = None if not skip_whole else [0, 0, 10, 10]
            view = await client.post(
                f"/v1/images/{task['image_id']}/views",
                json={"max_side": 2048, "crop_xywh": crop},
            )
            await emit(
                "observe", {"target": {"image_id": task["image_id"]}}, None, view
            )
            name = (await client.get(f"/v1/images/{task['image_id']}")).json()["name"]
            if name in unsearched:
                # Looked, and decided not to annotate (found 2026-10-16: an instruction told
                # it not to run).
                answer = {
                    "searched": False,
                    "not_searched_reason": "instruction says not to run yet",
                    "status": "not_detected",
                    "view_id": json.loads(view.headers["x-annotation-view"])["view_id"],
                    "explanation": "",
                }
                return answer, *read_usage(USAGE)
            if name in fail_names:
                raise ValueError("Observed failure from test model")
            saved = await client.post(
                f"/v1/results/{result_id}/annotations",
                json={
                    "request_id": str(uuid4()),
                    "base_revision": 0,
                    "operations": [
                        {
                            "op": "create",
                            "label": "circle",
                            "geometry": CIRCLE,
                            "attributes": {"color": "red"},
                        }
                    ],
                },
            )
            assert saved.status_code == 200, saved.text
            final = await client.post(f"/v1/results/{result_id}/views", json={})
            # How Codex's --json record shows a tool result over 1 MiB: its middle cut out,
            # the image as sent, or as a CLI encoding it again would hand it on.
            sent, shown = final.content, None
            if getattr(app.state, "cut_final", None) == "altered":
                page = io.BytesIO()
                Image.open(io.BytesIO(sent)).save(page, format="JPEG", quality=80)
                sent = page.getvalue()
            if getattr(app.state, "cut_final", None):
                data = base64.b64encode(sent).decode()
                shown = (
                    f"{data[:5000]}…{len(data) - 10000} chars truncated…{data[-5000:]}"
                )
            await emit(
                "observe", {"target": {"result_id": result_id}}, None, final, shown
            )
            await record(
                {
                    "type": "item.completed",
                    "item": {"id": "m", "type": "agent_message", "text": "done"},
                }
            )
            frame = json.loads(final.headers["x-annotation-view"])
            answer = {
                "searched": True,
                "not_searched_reason": "",
                "status": "detected",
                "view_id": frame["view_id"],
                "explanation": "円",
            }
            usage, evidence = read_usage(USAGE)
            return answer, usage, evidence

    return inference


def save_version(db, dataset, plan, by=PERSON):
    """A version of the plan saved for a test's setting: no route saves one by itself (a run
    decided makes it, definition 22.1), the function a run's decision uses."""
    return save_instruction(
        db, dataset, InstructionInput.model_validate(plan), by, decision_id=None
    )


def scenario(tmp_path, monkeypatch, body, **fake):
    """Run body(app, client, dataset_id, image_ids) with two imported images a.png and
    fail.png in a dataset with one instruction version."""

    async def main():
        app = create_app(tmp_path / "runs.db")
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
            ) as client,
        ):
            monkeypatch.setattr(runs_module, "infer", fake_inference(app, **fake))
            app.state.seen_refs = []
            monkeypatch.setattr(
                runs_module,
                "selected_execution_settings",
                lambda *_: {"model": "gpt-6-luna", "effort": "medium"},
            )
            # The Codex models a decision is checked by, whatever this machine's CLI cache
            # holds: the one the runs record (decisions name models of the catalog, 2026-10-28).
            monkeypatch.setattr(
                codex_execution,
                "codex_models",
                lambda: [
                    {
                        "model": "gpt-6-luna",
                        "display_name": "GPT-6-Luna",
                        "efforts": ["low", "medium", "high"],
                        "default_effort": "medium",
                        "speeds": [],
                    }
                ],
            )
            ids = {}
            for index, name in enumerate(("a.png", "fail.png")):
                path = tmp_path / name
                Image.new("RGB", (240, 120), (index * 40, 10, 10)).save(path)
                imported = await client.post(
                    "/v1/images/import", json={"paths": [str(path)]}
                )
                ids[name] = imported.json()["images"][0]["id"]
            dataset = (
                await client.post(
                    "/v1/datasets",
                    json={
                        "name": "円",
                        "purpose": "円を囲む",
                        "image_ids": list(ids.values()),
                    },
                )
            ).json()["id"]
            save_version(
                app.state.db,
                dataset,
                {"text": "円を囲む", "label_definitions": DEFINITIONS},
            )
            await body(app, client, dataset, ids)

    asyncio.run(main())


async def finished(client, run_id):
    """The run once it ended (it waits in the line of work, then runs; step 24)."""
    for _ in range(2000):
        state = (await client.get(f"/v1/runs/{run_id}")).json()
        if state["status"] not in ("queued", "running", "stopping"):
            return state
        await asyncio.sleep(0.01)
    raise AssertionError("The run did not end")


async def run_once(client, app, dataset, **body):
    run_id = str(uuid4())
    response = await client.put(f"/v1/datasets/{dataset}/runs/{run_id}", json=body)
    assert response.status_code == 201, response.text
    return await finished(client, run_id)


async def as_worker(client, app, dataset, image_id):
    """(the result id, the headers) of the worker of an image's result, its run made current
    again after it ended."""
    run = await run_once(client, app, dataset, image_ids=[image_id])
    result_id = (await client.get(f"/v1/runs/{run['id']}/results")).json()["results"][
        0
    ]["result_id"]
    manager = app.state.runs
    execution = RunExecution(app.state.db, run["id"], manager.notify, manager.jobs)
    execution.load()
    execution.take(
        dict(app.state.db.one("SELECT * FROM results WHERE id=?", (result_id,)))
    )
    manager.active[run["id"]] = execution
    return result_id, {
        "X-Annotation-Run-Id": run["id"],
        "X-Annotation-Result-Id": result_id,
    }


def test_run_keeps_results_and_what_the_worker_was_asked(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        run = await run_once(client, app, dataset)
        assert run["status"] == "failed" and run["error_code"] == "some_failed"
        assert (run["total"], run["succeeded"]) == (2, 1)
        instruction = (
            await client.get(f"/v1/datasets/{dataset}/instructions/latest")
        ).json()
        assert run["requirement_key"] == instruction["requirement_key"]
        assert run["requested"] == [
            {"label": "circle", "shape": "bbox", "attributes": ["color"]}
        ]
        prompt = app.state.db.one("SELECT worker_prompt FROM runs")[0]
        assert (
            run["worker_prompt_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
        )
        results = (await client.get(f"/v1/runs/{run['id']}/results")).json()["results"]
        status = {r["image_id"]: r["status"] for r in results}
        assert status == {ids["a.png"]: "detected", ids["fail.png"]: "failed"}
        good = next(r for r in results if r["status"] == "detected")
        state = (await client.get(f"/v1/results/{good['result_id']}")).json()
        assert [
            (a["label"], a["geometry"], a["attributes"]) for a in state["annotations"]
        ] == [("circle", CIRCLE, {"color": "red"})]

    scenario(tmp_path, monkeypatch, body)


def test_whole_target_must_be_seen(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        run = await run_once(client, app, dataset, image_ids=[ids["a.png"]])
        results = (await client.get(f"/v1/runs/{run['id']}/results")).json()["results"]
        assert results[0]["status"] == "failed"
        assert results[0]["message"] == "The whole target image was not observed"

    scenario(tmp_path, monkeypatch, body, skip_whole=True)


def test_only_the_worker_writes_its_own_result(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        run = await run_once(client, app, dataset)
        results = (await client.get(f"/v1/runs/{run['id']}/results")).json()["results"]
        batch = {
            "base_revision": 1,
            "operations": [{"op": "delete", "id": "ann-x"}],
        }
        outsider = await client.post(
            f"/v1/results/{results[0]['result_id']}/annotations", json=batch
        )
        other = await client.post(
            f"/v1/results/{results[0]['result_id']}/annotations",
            json=batch,
            headers={
                "X-Annotation-Run-Id": run["id"],
                "X-Annotation-Result-Id": results[1]["result_id"],
            },
        )
        assert outsider.status_code == other.status_code == 403
        assert (
            outsider.json()["error"]["code"]
            == other.json()["error"]["code"]
            == "run_scope"
        )

    scenario(tmp_path, monkeypatch, body)


def test_coordinates_on_a_shrunk_view_are_saved_in_original_pixels(
    tmp_path, monkeypatch
):
    async def body(app, client, dataset, ids):
        result_id, worker = await as_worker(client, app, dataset, ids["a.png"])
        small = await client.post(
            f"/v1/images/{ids['a.png']}/views",
            json={"max_side": 120},
            headers=worker,
        )
        frame = json.loads(small.headers["x-annotation-view"])
        assert frame["output_size"] == [120, 60]
        saved = await client.post(
            f"/v1/results/{result_id}/annotations",
            json={
                "base_revision": 1,
                "coordinate_view_id": frame["view_id"],
                "operations": [
                    {
                        "op": "create",
                        "label": "circle",
                        "geometry": {"type": "bbox", "xywh": [10, 5, 20, 10]},
                    }
                ],
            },
            headers=worker,
        )
        assert saved.status_code == 200, saved.text
        made = [
            a
            for a in saved.json()["annotations"]
            if a["id"] in saved.json()["created_ids"]
        ]
        assert made[0]["geometry"]["xywh"] == [20, 10, 40, 20]

    scenario(tmp_path, monkeypatch, body)


def test_a_reference_is_a_result_of_its_image_by_the_plan_now(tmp_path, monkeypatch):
    # Definition 38.1 (user 2026-10-23): only the workers and people's fixes write annotations;
    # a reference is a result of the image chosen, of the plan's labels now.
    async def body(app, client, dataset, ids):
        run = await run_once(client, app, dataset)
        results = {
            r["image_id"]: r["result_id"]
            for r in (await client.get(f"/v1/runs/{run['id']}/results")).json()[
                "results"
            ]
        }
        base = f"/v1/datasets/{dataset}/images"

        async def choose(image, result_id):
            return await client.put(
                f"{base}/{image}/reference",
                json={"result_id": result_id, "note": "赤い円"},
            )

        other = await choose(ids["fail.png"], results[ids["a.png"]])
        failed = await choose(ids["fail.png"], results[ids["fail.png"]])
        assert other.status_code == failed.status_code == 422
        chosen = await choose(ids["a.png"], results[ids["a.png"]])
        assert chosen.status_code == 200, chosen.text
        shown = (await client.get(f"{base}/{ids['a.png']}/reference")).json()
        assert [a["geometry"] for a in shown["annotations"]] == [CIRCLE]
        assert shown["note"] == "赤い円"
        # Another label in the plan: a result of the labels before is not of the plan now.
        square = {"name": "square", "shape": "bbox", "attributes": []}
        written = await client.put(
            f"/v1/datasets/{dataset}/drafts/instruction",
            json={"label_definitions": [*DEFINITIONS, square]},
        )
        assert written.status_code == 200, written.text
        stale = await choose(ids["a.png"], results[ids["a.png"]])
        assert stale.json()["error"]["code"] == "requirement_mismatch"

    scenario(tmp_path, monkeypatch, body)


def test_a_reference_reaches_the_workers_and_its_image_is_not_annotated(
    tmp_path, monkeypatch
):
    # Definition 38.1: a reference image's annotation is the reference, so no run takes it,
    # named or not; the workers of the other images get it.
    async def body(app, client, dataset, ids):
        first = await run_once(client, app, dataset, image_ids=[ids["a.png"]])
        result_id = (await client.get(f"/v1/runs/{first['id']}/results")).json()[
            "results"
        ][0]["result_id"]
        chosen = await client.put(
            f"/v1/datasets/{dataset}/images/{ids['a.png']}/reference",
            json={"result_id": result_id, "note": "赤い円"},
        )
        assert chosen.status_code == 200, chosen.text
        named = await client.put(
            f"/v1/datasets/{dataset}/runs/{uuid4()}",
            json={"image_ids": [ids["a.png"]]},
        )
        assert named.status_code == 422, named.text
        # A worker's box naming it is refused with its name, so the box says what will run
        # (2026-10-29: titled "all 4 images", 3 would run; definition 74).
        boxed = await client.post(
            f"/v1/datasets/{dataset}/proposals",
            json={
                "agent": "steward",
                "tool": "run_start",
                "args": {"image_ids": [ids["a.png"], ids["fail.png"]]},
                "title": "2枚とも",
                "reason": "r",
            },
        )
        assert boxed.status_code == 422, boxed.text
        assert boxed.json()["error"]["details"]["images"] == ["a.png"]
        run = await run_once(client, app, dataset)
        results = (await client.get(f"/v1/runs/{run['id']}/results")).json()["results"]
        assert [r["image_id"] for r in results] == [ids["fail.png"]]
        ((target, ref, frame),) = app.state.seen_refs
        assert (target, ref["image_id"], ref["note"]) == (
            ids["fail.png"],
            ids["a.png"],
            "赤い円",
        )
        assert frame["image_id"] == ref["image_id"]
        assert len(frame["annotation_ids"]) == 1
        # Cropped around the example with the margin every crop gets (20 px of the original,
        # definition 30.1), enlarged to the run's view size (at most 8x).
        assert frame["crop_xywh"] == [80, 30, 80, 70]
        assert frame["output_size"] == [640, 560]

    scenario(tmp_path, monkeypatch, body)


def test_a_busy_provider_is_tried_again(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        # Found 2026-10-05: "Selected model is at capacity" failed images for good.
        await client.put("/v1/settings", json={"retry_wait_seconds": 5})
        real, tries = runs_module.infer, []

        async def busy_once(directory, run, result_id, stop, record):
            tries.append(result_id)
            if len(tries) == 1:
                raise RuntimeError(
                    "CLI execution failed (exit=1, completed_turns=0): "
                    "Selected model is at capacity. Please try a different model."
                )
            return await real(directory, run, result_id, stop, record)

        monkeypatch.setattr(runs_module, "infer", busy_once)
        run = await run_once(client, app, dataset, image_ids=[ids["a.png"]])
        assert run["status"] == "succeeded" and tries[0] == tries[1]
        logs = (await client.get(f"/v1/runs/{run['id']}/logs?limit=1000")).json()
        messages = [
            e["payload"].get("message") or ""
            for e in next(v for v in logs.values() if isinstance(v, list))
            if e["kind"] == "state"
        ]
        assert any("Trying again" in m and "at capacity" in m for m in messages)

    scenario(tmp_path, monkeypatch, body)


def test_each_images_worker_waits_for_the_memory_it_takes(tmp_path, monkeypatch):
    # 2026-11-02: the line looked at the memory when a run started only; the run's worker
    # CLIs, started with the memory gone, ended at once.
    async def body(app, client, dataset, ids):
        free, first, started = {"mb": 0}, [100_000], []
        # Enough when the line starts the run, none when its image is to start.
        monkeypatch.setattr(jobs_module, "WORKER_MB", 450)
        app.state.jobs.memory = lambda: first.pop() if first else free["mb"]
        monkeypatch.setattr(runs_module, "MEMORY_RECHECK_SECONDS", 0.01)
        real = runs_module.infer

        async def counted(directory, run, result_id, stop, record):
            started.append(result_id)
            return await real(directory, run, result_id, stop, record)

        monkeypatch.setattr(runs_module, "infer", counted)
        run_id = str(uuid4())
        asked = await client.put(
            f"/v1/datasets/{dataset}/runs/{run_id}", json={"image_ids": [ids["a.png"]]}
        )
        assert asked.status_code == 201
        for _ in range(500):
            listed = (await client.get("/v1/jobs")).json()["jobs"]
            job = next(j for j in listed if j["run_id"] == run_id)
            if job["state"] == "running" and job["wait_reason"] == "memory":
                break
            await asyncio.sleep(0.01)
        assert job["memory"] == {"free_mb": 0, "need_mb": jobs_module.memory_needed(1)}
        assert started == []
        free["mb"] = 100_000
        assert (await finished(client, run_id))["status"] == "succeeded"
        assert len(started) == 1

    scenario(tmp_path, monkeypatch, body)


def test_an_image_failed_while_the_memory_is_short_says_so(tmp_path, monkeypatch):
    # 2026-11-02: with the memory gone, the worker CLIs ended at once, and the image said only
    # "CLI execution failed (exit=1, completed_turns=0)", the run "Some images failed".
    async def body(app, client, dataset, ids):
        free = {"mb": 100_000}
        monkeypatch.setattr(jobs_module, "WORKER_MB", 450)
        app.state.jobs.memory = lambda: free["mb"]

        async def memory_gone(directory, run, result_id, stop, record):
            free["mb"] = 10
            raise RuntimeError("CLI execution failed (exit=1, completed_turns=0)")

        monkeypatch.setattr(runs_module, "infer", memory_gone)
        run = await run_once(client, app, dataset, image_ids=[ids["a.png"]])
        assert (run["status"], run["error_code"]) == ("failed", "memory_short")
        said = app.state.db.one(
            "SELECT message FROM results WHERE run_id=?", (run["id"],)
        )["message"]
        assert said.startswith("Not enough memory") and "exit=1" in said

    scenario(tmp_path, monkeypatch, body)


def test_a_trial_runs_the_version_and_an_instruction_can_start_from_another_dataset(
    tmp_path, monkeypatch
):
    async def body(app, client, dataset, ids):
        latest = (
            await client.get(f"/v1/datasets/{dataset}/instructions/latest")
        ).json()
        # A trial runs the saved version on a few images, a run like any (user 2026-10-13).
        run = await run_once(client, app, dataset, trial=True, image_ids=[ids["a.png"]])
        assert (run["instruction_revision"], run["trial"]) == (1, True)
        # A label only in the draft gets its color too (found 2026-10-05: KeyError on trial).
        draft = {
            "text": "試しの指示",
            "label_definitions": [
                *latest["label_definitions"],
                {"name": "square", "shape": "bbox"},
            ],
        }
        await client.put(f"/v1/datasets/{dataset}/drafts/instruction", json=draft)
        # What a worker would get, from the draft, by the same function a run uses.
        view = (
            await client.get(f"/v1/datasets/{dataset}/worker-view?draft=true")
        ).json()
        assert view["task"]["instruction_text"] == "試しの指示"
        assert view["task"]["label_colors"]["square"]
        assert "result_id" in view["worker_prompt"]

        other = (
            await client.post(
                "/v1/datasets",
                json={"name": "別", "purpose": "同じ物", "image_ids": []},
            )
        ).json()["id"]
        found = (await client.get("/v1/instruction-sources?q=circle")).json()["sources"]
        assert dataset in [s["dataset_id"] for s in found]
        copied = await client.post(
            f"/v1/datasets/{other}/instruction-from", json={"dataset_id": dataset}
        )
        assert copied.status_code == 201, copied.text
        made = (await client.get(f"/v1/datasets/{other}/drafts/instruction")).json()
        assert made["label_definitions"] == latest["label_definitions"]
        assert made["references"] == []
        again = await client.post(
            f"/v1/datasets/{other}/instruction-from", json={"dataset_id": dataset}
        )
        assert again.status_code == 409

    scenario(tmp_path, monkeypatch, body)


def test_a_trial_is_a_run_of_the_saved_version_and_is_used_for_training(
    tmp_path, monkeypatch
):
    """User 2026-10-13: a trial runs the saved version, so its results are the version's like a
    run's (shown in ② as annotated, used by the rule); before, a trial of a draft never was."""

    async def body(app, client, dataset, ids):
        a, failing = ids["a.png"], ids["fail.png"]
        trial = await run_once(client, app, dataset, trial=True, image_ids=[a])
        runs = {
            r["id"]: r
            for r in (await client.get(f"/v1/datasets/{dataset}/runs")).json()["runs"]
        }
        assert runs[trial["id"]]["trial"]
        facts = (await client.get(f"/v1/datasets/{dataset}/progress")).json()["facts"]
        assert (facts["runs"], facts["with_result"]) == (1, 1)
        page = (await client.get(f"/v1/datasets/{dataset}/gallery?view=run")).json()
        badges = {i["image"]["id"]: i["badge"] for i in page["items"]}
        assert (badges[a]["kind"], badges[a]["record_id"]) == ("detected", trial["id"])
        assert badges[failing]["kind"] == "no_result"
        adopted = (await client.get(f"/v1/datasets/{dataset}/adoption")).json()
        found = {i["image_id"]: i for i in adopted["items"]}[a]
        assert (found["source"], found["run_id"]) == ("result", trial["id"])

    scenario(tmp_path, monkeypatch, body)


def test_a_label_in_none_of_the_samples_is_said(tmp_path, monkeypatch):
    # Definition 38.5 (user 2026-10-23): samples show only what their images have, so a label
    # the plan defines may be in none of them; the screen says so.
    async def body(app, client, dataset, ids):
        dot = {"name": "dot", "shape": "bbox", "attributes": []}
        written = await client.put(
            f"/v1/datasets/{dataset}/drafts/instruction",
            json={"label_definitions": [*DEFINITIONS, dot]},
        )
        assert written.status_code == 200, written.text
        trial = await run_once(
            client, app, dataset, trial=True, image_ids=[ids["a.png"]]
        )
        record = f"/v1/datasets/{dataset}/gallery?view=run&record_id={trial['id']}"
        page = (await client.get(record)).json()
        assert page["missing_labels"] == ["dot"]
        # Not while the samples are annotated (test 10-28: said before they were done).
        app.state.db.execute(
            "UPDATE runs SET status='running' WHERE id=?", (trial["id"],)
        )
        assert (await client.get(record)).json()["missing_labels"] == []

    scenario(tmp_path, monkeypatch, body)


def test_a_trial_of_an_earlier_version_keeps_its_record_on_the_cards(
    tmp_path, monkeypatch
):
    """Sol 2026-10-14: after a version with other labels, a trial of version 1 showed no record
    number nor "trial" on its card in ②, and "no result yet" in ①."""

    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        trial = await run_once(client, app, dataset, trial=True, image_ids=[a])
        save_version(
            app.state.db,
            dataset,
            {
                "text": "円を囲む",
                "label_definitions": [*DEFINITIONS, {"name": "dot", "shape": "bbox"}],
            },
        )
        for view in ("run", "production"):
            page = (
                await client.get(f"/v1/datasets/{dataset}/gallery?view={view}")
            ).json()
            badge = {i["image"]["id"]: i["badge"] for i in page["items"]}[a]
            assert (badge["kind"], badge["record_id"], badge["record_number"]) == (
                "stale",
                trial["id"],
                1,
            )
            assert (badge["earlier_revision"], badge["trial"]) == (1, True)

    scenario(tmp_path, monkeypatch, body)


def test_an_image_left_out_of_training_is_annotated_too(tmp_path, monkeypatch):
    """User 2026-10-14: using for training and annotating are apart (a poor annotation is left
    out of training, then done again), so a run of every image takes it too."""

    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        left = await client.post(f"/v1/datasets/{dataset}/images/{a}/exclude", json={})
        assert left.status_code == 200, left.text
        run = await run_once(client, app, dataset)
        results = (await client.get(f"/v1/runs/{run['id']}/results")).json()["results"]
        assert a in {r["image_id"] for r in results}

    scenario(tmp_path, monkeypatch, body)


def test_deleting_counts_a_trial_as_a_trial(tmp_path, monkeypatch):
    """User 2026-10-15: the count before deleting still took trials for runs of the draft."""

    async def body(app, client, dataset, ids):
        await run_once(client, app, dataset, trial=True, image_ids=[ids["a.png"]])
        await run_once(client, app, dataset)
        found = (await client.get(f"/v1/datasets/{dataset}/deletion")).json()
        assert (found["runs"], found["trials"]) == (1, 1)

    scenario(tmp_path, monkeypatch, body)


def test_deleting_datasets_deletes_the_images_no_other_dataset_uses(
    tmp_path, monkeypatch
):
    """User 2026-10-15: what no dataset uses is seen nowhere, so its rows and files go; images
    another dataset uses stay, and the preview says which."""

    async def body(app, client, dataset, ids):
        copy = (
            await client.post(
                f"/v1/datasets/{dataset}/copy",
                json={"name": "写し", "purpose": "円を囲む", "instruction": False},
            )
        ).json()["id"]
        files = lambda: sorted(p.name for p in app.state.db.files.root.rglob("*.png"))
        stored = files()
        assert len(stored) == 2
        seen = (await client.get(f"/v1/datasets/{dataset}/deletion")).json()
        assert (seen["freed_images"], seen["shared"][0]["images"]) == (0, 2)
        both = (
            await client.post(
                "/v1/datasets/deletion", json={"dataset_ids": [dataset, copy]}
            )
        ).json()
        assert (both["freed_images"], both["shared"]) == (2, [])
        assert (await client.delete(f"/v1/datasets/{dataset}")).json()[
            "removed_images"
        ] == 0
        assert files() == stored
        gone = (await client.delete(f"/v1/datasets/{copy}")).json()
        assert gone["removed_images"] == 2 and files() == []
        listed = (await client.get("/v1/datasets")).json()
        assert listed["stored"] == {"images": 0, "bytes": 0}

    scenario(tmp_path, monkeypatch, body)


def test_deleting_two_datasets_counts_what_a_third_keeps_once(tmp_path, monkeypatch):
    """Found 2026-10-15: two chosen datasets with the same images counted the size the third
    keeps twice."""

    async def body(app, client, dataset, ids):
        made = []
        for name in ("写し1", "写し2"):
            made.append(
                (
                    await client.post(
                        f"/v1/datasets/{dataset}/copy",
                        json={"name": name, "purpose": "円", "instruction": False},
                    )
                ).json()["id"]
            )
        size = next(
            d["bytes"]
            for d in (await client.get("/v1/datasets")).json()["datasets"]
            if d["id"] == dataset
        )
        seen = (
            await client.post(
                "/v1/datasets/deletion", json={"dataset_ids": [dataset, made[0]]}
            )
        ).json()
        assert [(s["dataset_id"], s["images"], s["bytes"]) for s in seen["shared"]] == [
            (made[1], 2, size)
        ]

    scenario(tmp_path, monkeypatch, body)


def test_a_dataset_is_made_from_several_with_each_image_once(tmp_path, monkeypatch):
    """User 2026-10-15: making from several datasets, the shared images once."""

    async def body(app, client, dataset, ids):
        only_a = (
            await client.post(
                "/v1/datasets",
                json={"name": "a", "purpose": "円", "image_ids": [ids["a.png"]]},
            )
        ).json()["id"]
        made = await client.post(
            "/v1/datasets/from",
            json={"name": "合わせ", "purpose": "円", "dataset_ids": [only_a, dataset]},
        )
        assert made.status_code == 201, made.text
        images = [i["image_id"] for i in made.json()["images"]]
        assert images == [ids["a.png"], ids["fail.png"]]

    scenario(tmp_path, monkeypatch, body)


def test_every_workers_views_stay_inside_what_every_model_takes_in(
    tmp_path, monkeypatch
):
    # Found 2026-10-07: with views of 1536 px, a Claude worker got its 1024x1536 view scaled
    # down by Claude Code, other bytes than sent, and the run failed "not observed". User:
    # every model gets the same size, one none scales down; the setting goes up to 1024.
    import io
    from types import SimpleNamespace

    from agent_app.imaging import render
    from agent_app.model_catalog import WORKER_VIEW_MAX_PIXELS
    from agent_app.run_routes import worker_size
    from agent_app.shapes import ViewRequest
    from PIL import Image

    def request_of(model):
        # A run started before the setting's range narrowed (1536).
        settings = {"worker_view_max_side": 1536, "model": model}
        execution = SimpleNamespace(run={"settings": settings})
        state = SimpleNamespace(runs=SimpleNamespace(execution=lambda _id: execution))
        return SimpleNamespace(app=SimpleNamespace(state=state))

    body = ViewRequest(overlay=False)
    sizes = {
        model: worker_size(request_of(model), ("run", "result"), body)
        for model in ("claude-opus-5-5", "gpt-6.1-sol")
    }
    assert {v.max_pixels for v in sizes.values()} == {WORKER_VIEW_MAX_PIXELS}
    page = io.BytesIO()
    Image.new("RGB", (1024, 1536), "white").save(page, format="PNG")
    _, frame = render(page.getvalue(), [], sizes["gpt-6.1-sol"], {})
    width, height = frame["output_size"]
    assert (
        width * height <= WORKER_VIEW_MAX_PIXELS and abs(width / height - 2 / 3) < 0.01
    )

    async def body_of(app, client, dataset, ids):
        refused = await client.put("/v1/settings", json={"worker_view_max_side": 1536})
        assert refused.status_code == 422
        with app.state.db.transaction():
            app.state.db.execute(
                "INSERT OR REPLACE INTO app_settings(key, value_json, updated_at)"
                " VALUES('worker_view_max_side', '1536', '2026-10-07T00:00:00Z')"
            )
        read = (await client.get("/v1/settings")).json()
        assert read["worker_view_max_side"] == 1024

    scenario(tmp_path, monkeypatch, body_of)


def test_a_view_whose_record_the_cli_cut_is_seen_unless_its_bytes_differ(
    tmp_path, monkeypatch
):
    # Found 2026-10-29: Codex's --json record cuts a tool result over 1 MiB in the middle. Its
    # model still got the image whole (it read the top and the bottom of a 1.6 MB one), but
    # the check found no bytes to match and failed 4 of 50 images. What the cut leaves is
    # matched with the view drawn again; bytes a CLI encoded again still fail.
    async def body(app, client, dataset, ids):
        path = tmp_path / "noisy.png"
        Image.frombytes("RGB", (600, 400), os.urandom(600 * 400 * 3)).save(path)
        imported = await client.post("/v1/images/import", json={"paths": [str(path)]})
        image = imported.json()["images"][0]["id"]
        await client.post(f"/v1/datasets/{dataset}/images", json={"image_ids": [image]})
        for mode, status in (("same", "detected"), ("altered", "failed")):
            app.state.cut_final = mode
            run = await run_once(client, app, dataset, image_ids=[image])
            results = (await client.get(f"/v1/runs/{run['id']}/results")).json()
            assert results["results"][0]["status"] == status, results

    scenario(tmp_path, monkeypatch, body)


def test_haiku_5_5_is_offered_and_priced_with_its_short_prompt_prices():
    # User 2026-10-08: Haiku 5.5 is out, make it usable (priced by each request's prompt).
    from agent_app.costs import api_cost
    from agent_app.model_catalog import CLAUDE_PRICE_VERSION, claude_models

    assert "claude-haiku-5-5" in [m["model"] for m in claude_models()]
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "cached_input_tokens": 0,
        "cache_write_input_tokens": 0,
        "raw": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0},
        "inclusion": {
            "cached_input_tokens": "external",
            "cache_write_input_tokens": "external",
        },
    }
    cost = api_cost(
        usage,
        {
            "model": "claude-haiku-5-5",
            "tier": "standard",
            "api_price_version": CLAUDE_PRICE_VERSION,
            "usd_to_jpy": "160",
        },
    )
    assert float(cost["usd"]) == 0.60
    assert cost["basis"]["context"] == "short_assumed_per_request"
    assert any("100000 tokens or less" in a for a in cost["assumptions"])


def test_gpt_6_1_terra_is_priced_so_its_cost_and_limit_hold():
    # User 2026-10-27: GPT-6.1 Terra is out, make it usable. The CLI's catalog offered it, but
    # without a price its cost was unknown and a run's cost limit never stopped it.
    from agent_app.costs import api_cost
    from agent_app.model_catalog import API_PRICE_VERSION

    cost = api_cost(
        {
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "cached_input_tokens": 0,
        },
        {
            "model": "gpt-6.1-terra",
            "api_price_version": API_PRICE_VERSION,
            "usd_to_jpy": "160",
        },
    )
    assert (cost["missing_reason"], float(cost["usd"])) == (None, 6.0)


def test_an_image_not_searched_is_a_failure_with_its_reason(tmp_path, monkeypatch):
    """Found 2026-10-16: a worker that decided not to annotate could only answer
    not_detected, a success that training used; it answers searched=false now."""

    async def body(app, client, dataset, ids):
        started = await client.put(
            f"/v1/datasets/{dataset}/runs/{uuid4()}",
            json={"image_ids": [ids["a.png"]]},
        )
        run = await finished(client, started.json()["id"])
        result = (await client.get(f"/v1/runs/{run['id']}/results")).json()["results"][
            0
        ]
        assert result["status"] == "failed"
        assert "instruction says not to run yet" in result["message"]
        training = (await client.get(f"/v1/datasets/{dataset}/adoption")).json()
        assert training["items"][0]["source"] != "result"

    scenario(tmp_path, monkeypatch, body, unsearched=("a.png",))


def test_a_runs_images_go_at_once(tmp_path, monkeypatch):
    # Definition 50.2 (user 2026-10-26): a run's images went one at a time, so a 3-image run
    # took the three's sum.
    async def body(app, client, dataset, ids):
        await client.put("/v1/settings", json={"image_slots": 2})
        real, going, most = runs_module.infer, [0], [0]

        async def counted(directory, run, result_id, stop, record):
            going[0] += 1
            most[0] = max(most[0], going[0])
            try:
                await asyncio.sleep(0.05)
                return await real(directory, run, result_id, stop, record)
            finally:
                going[0] -= 1

        monkeypatch.setattr(runs_module, "infer", counted)
        run = await run_once(client, app, dataset)
        assert (run["total"], most[0]) == (2, 2)

    scenario(tmp_path, monkeypatch, body)


def test_a_run_stopped_at_its_cost_limit_says_so(tmp_path, monkeypatch):
    # Definition 50.3: stopped at the cost limit, the screen said "stopped" as when a person
    # stops it; the line of its end carries why and the limit.
    async def body(app, client, dataset, ids):
        await client.put("/v1/settings", json={"image_slots": 1})
        run = await run_once(client, app, dataset, budget_per_image_usd="0.0001")
        assert (run["status"], run["error_code"]) == ("stopped", "budget_reached")
        ended = [
            json.loads(r[0])
            for r in app.state.db.execute(
                "SELECT data_json FROM agent_events WHERE text='run_ended'"
            )
        ]
        assert (ended[-1]["error_code"], ended[-1]["budget_per_image_usd"]) == (
            "budget_reached",
            "0.0001",
        )

    scenario(tmp_path, monkeypatch, body)


def test_a_run_held_for_memory_starts_once_memory_frees(tmp_path, monkeypatch):
    # 2026-10-28 (Windows, just started): a run held for memory waited for ever, the line being
    # looked at again only when a job ended or was asked; memory frees with no such event.
    from agent_app import jobs as jobs_module

    monkeypatch.setattr(jobs_module, "MEMORY_RECHECK_SECONDS", 0.05)
    monkeypatch.setattr(jobs_module, "FLOOR_MB", 4096)
    monkeypatch.setattr(jobs_module, "WORKER_MB", 300)

    async def body(app, client, dataset, ids):
        free = [0]
        app.state.jobs.memory = lambda: free[0]
        run_id = str(uuid4())
        started = await client.put(
            f"/v1/datasets/{dataset}/runs/{run_id}", json={"image_ids": [ids["a.png"]]}
        )
        assert started.status_code == 201, started.text
        await asyncio.sleep(0.1)
        (job,) = (await client.get("/v1/jobs")).json()["jobs"]
        assert (job["state"], job["wait_reason"]) == ("queued", "memory")
        # How much is free and how much it waits for (2026-10-30: the talk said only
        # "thinking"): the floor and the run's worker CLIs.
        assert job["memory"] == {"free_mb": 0, "need_mb": 4096 + 300 * 3}
        free[0] = 100_000
        assert (await finished(client, run_id))["status"] == "succeeded"

    scenario(tmp_path, monkeypatch, body)


def test_a_run_given_no_limit_takes_twice_its_ways_cost_else_the_settings(
    tmp_path, monkeypatch
):
    # Definition 65, 84 (user 2026-10-28, 10-30): the limit is per image; a run given none takes
    # twice what one image cost by its way (model and effort) before, else the settings'.
    from decimal import ROUND_UP, Decimal

    from agent_app.instructions import latest_requirement
    from agent_app.usage import expected_cost

    async def body(app, client, dataset, ids):
        run = await run_once(client, app, dataset)
        assert run["budget_per_image_usd"] == "2"
        await client.put("/v1/settings", json={"run_budget_per_image_usd": 0.25})
        again = await run_once(client, app, dataset)
        cost = expected_cost(
            app.state.db,
            dataset,
            latest_requirement(app.state.db, dataset),
            ("gpt-6-luna", "medium"),
        )
        twice = (2 * cost["per_image_usd"]).quantize(Decimal("0.01"), rounding=ROUND_UP)
        assert again["budget_per_image_usd"] == str(twice)
        # A plan no way ran yet (another dataset, another requirement): the settings'.
        made = await client.post(
            "/v1/datasets",
            json={"name": "四角", "purpose": "四角", "image_ids": [ids["a.png"]]},
        )
        square = [{"name": "square", "shape": "bbox", "attributes": []}]
        save_version(
            app.state.db,
            made.json()["id"],
            {"text": "四角", "label_definitions": square},
        )
        other = await run_once(client, app, made.json()["id"])
        assert other["budget_per_image_usd"] == "0.25"

    scenario(tmp_path, monkeypatch, body)


def test_the_images_are_counted_by_state_where_they_are_shown(tmp_path, monkeypatch):
    """Definition 57 (user 2026-10-27): the library's card said how far the annotation came only
    in hovers, and the annotating screen put two plans' numbers side by side. The images are
    counted by state once (image_state.state_counts), the same on the card and the screens."""

    async def body(app, client, dataset, ids):
        run = await run_once(client, app, dataset)
        # While a run goes (found 10-27: its own count overwrote the images', a 500 and a blank
        # screen for as long as it ran).
        app.state.db.execute(
            "UPDATE runs SET status='running' WHERE id=?", (run["id"],)
        )
        going = await client.get(f"/v1/datasets/{dataset}/progress")
        assert going.status_code == 200
        assert going.json()["facts"]["running"]["run_id"] == run["id"]
        app.state.db.execute(
            "UPDATE runs SET status='succeeded' WHERE id=?", (run["id"],)
        )
        progress = (await client.get(f"/v1/datasets/{dataset}/progress")).json()
        counts = progress["facts"]["counts"]
        parts = ("done", "running", "failed", "stale", "none")
        assert sum(counts[k] for k in parts) == counts["images"]
        assert counts["failed"] == 1  # fail.png
        assert (counts["done"], counts["used"]) == (
            progress["facts"]["with_result"],
            progress["facts"]["adopted"],
        )
        page = (await client.get(f"/v1/datasets/{dataset}/gallery?view=run")).json()
        assert page["counts"] == counts
        listed = next(
            d
            for d in (await client.get("/v1/datasets")).json()["datasets"]
            if d["id"] == dataset
        )
        assert listed["labels"] and listed["last_at"] > listed["created_at"]

    scenario(tmp_path, monkeypatch, body)


def test_a_records_gallery_reads_the_plan_the_record_holds(tmp_path, monkeypatch):
    """Found 2026-10-27: a trial of a draft made before trials had versions (revision 0, three
    on the main data) failed its record's whole gallery ("Instruction version does not exist"):
    the labels none of its results has were read from version 0. A record's plan is the one it
    holds (run_queries.ran_plan), as its worker was given."""

    async def body(app, client, dataset, ids):
        run = await run_once(client, app, dataset, trial=True, image_ids=[ids["a.png"]])
        app.state.db.execute(
            "UPDATE runs SET instruction_revision=0 WHERE id=?", (run["id"],)
        )
        page = await client.get(
            f"/v1/datasets/{dataset}/gallery?view=run&record_id={run['id']}"
        )
        assert page.status_code == 200, page.text
        assert "missing_labels" in page.json()

    scenario(tmp_path, monkeypatch, body)
