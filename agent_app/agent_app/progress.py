"""The overall map's two stages, ① making the plan and ② carrying it out (types design 5 and 17:
the inspection stage and the masters were taken out on 2026-10-13), computed from the data every
time and never stored (docs/2026-10-05-app-step6-design.md 3, data-model 11.1).

What to do now comes from the state of things, not from a fixed walk of the stages with a
sentence per stage (user 2026-10-12: "the person does not necessarily say what they will do
next"; "it is not always a few images that are run"): a run going, the plan's next step while
a draft is being made, the images with nothing for training, or all done. The plan is made
when it was tried as it is (definition 26.3: a person ran it, so decided all of it).
"""

from .datasets import dataset_row, image_count
from .image_state import image_states, state_counts
from .instructions import latest_basis, latest_row
from .plan_state import plan_state
from .run_queries import (
    GOING,
    dataset_runs,
    of_requirement,
    record_results,
    result_counts,
)

# The keys stay as they were (the screens and the records use them); the names are the
# screen's ("計画", "AI でアノテーションする"; what 計画 makes is the 計画書, user 2026-10-15).
STAGES = ("instruction", "production")


def progress(db, dataset_id):
    dataset_row(db, dataset_id)
    images = image_count(db, dataset_id)
    latest = latest_row(db, dataset_id)
    state = plan_state(db, dataset_id)
    facts = {
        "images": images,
        "revision": latest["revision"] if latest else None,
        # ① from the inside: who decided each item of the plan, the next to ask, and whether a
        # draft is the plan now (the next run keeps it as a version).
        "instruction": {
            "items": state["items"],
            "next": state["next"],
            "draft": state["write_id"] is not None,
        },
    }
    done = {stage: False for stage in STAGES}
    running = None
    if latest:
        key = latest["requirement_key"]
        done["instruction"] = next(
            i["status"] == "person" for i in state["items"] if i["item"] == "trial"
        )
        runs = [r for r in dataset_runs(db, dataset_id) if of_requirement(r, key)]
        active = [r for r in runs if r["status"] in GOING]
        _, states = image_states(db, dataset_id, *latest_basis(db, dataset_id))
        # How many of the dataset's images have a result of the requirement (user 2026-10-07:
        # "4 runs" did not tell how much of the dataset was done, so whether to run again), and
        # in each state (definition 57: the library's card).
        by_state = state_counts(states)
        with_result = by_state["done"]
        if active:
            # The run going's own count, apart from the images' (it overwrote them, 10-27).
            going = result_counts(
                r["status"] for r in record_results(db, active[0]["id"])
            )
            running = {
                "run_id": active[0]["id"],
                "total": going["total"],
                "done": going["processed"],
                "stage": "production",
            }
        adopted = by_state["used"]
        needed = by_state["images"] - by_state["excluded"]
        facts.update(
            runs=len(runs),
            counts=by_state,
            with_result=with_result,
            running=running,
            adopted=adopted,
            needed=needed,
        )
        # Done when every image has something for training: what is chosen is what training
        # uses, recorded when it is used, with no fixing (user 2026-10-15).
        done["production"] = needed > 0 and adopted >= needed
    if running:
        now = "production"
    elif not done["instruction"]:
        now = "instruction"  # the plan as it is not run yet: it is made first
    elif not done["production"]:
        now = "production"
    else:
        now = None
    return {
        "stages": [
            {
                "stage": s,
                "state": "now" if s == now else "done" if done[s] else "todo",
            }
            for s in STAGES
        ],
        "facts": facts,
        "overall": _overall(now, running, facts),
    }


def _overall(now, running, facts):
    """One line for the whole dataset, from the state of things: running, the plan's next
    step, the images with nothing for training, the annotations made by an earlier plan's
    criteria and not checked (definition 85.6: run again or check), or complete."""
    if running:
        return {"kind": "running", **running}
    if now is None:
        other = facts["counts"]["other"]
        if other:
            return {"kind": "other", "stage": "production", "count": other}
        return {"kind": "complete", "count": facts.get("adopted", 0)}
    if now == "production":
        missing = facts.get("needed", 0) - facts.get("adopted", 0)
        return {"kind": "missing", "stage": "production", "count": missing}
    return {"kind": "next", "stage": now}
