"""What a run starts from (step 2 design, step 12 and 14): the images, the plan it runs (a draft
write or a version, held by value; definition 11.3), its way of running and, when nothing is
chosen, the settings' default model and effort.
"""

import json
from decimal import ROUND_UP, Decimal

from .datasets import image_ids
from .db import new_id, now
from .drafts import plan_at, plan_of
from .errors import ApiError, invalid
from .image_state import writing
from .run_queries import dataset_runs, of_version
from .settings import read_settings
from .usage import expected_cost


def last_ai_run(db, dataset_id):
    """The dataset's latest run of a plan version, in the order runs were made (the wall clock
    can step back): what "the way last run" and the default choice go on from. A person's fix
    is not a run (definition 21.4)."""
    return next(
        (r for r in reversed(dataset_runs(db, dataset_id)) if of_version(r)),
        None,
    )


def last_choice(db, dataset_id):
    """The model, effort and speed of the dataset's latest run (last_ai_run), as the workers are
    told it; (None, None, None) without one."""
    row = last_ai_run(db, dataset_id)
    if row is None:
        return None, None, None
    settings = json.loads(row["settings_json"])
    tier = settings.get("tier")
    return (
        settings.get("model"),
        settings.get("effort"),
        tier if tier not in (None, "default", "standard") else None,
    )


def default_choice(db):
    """The model, effort and speed a run takes when none is chosen, one for every way in (issue
    #5-10: a box, a person's preview and a run of nothing chosen took different defaults): the
    settings' default at the standard speed, the same for every dataset (user 2026-10-27)."""
    chosen = read_settings(db)
    return chosen["run_model"], chosen["run_effort"], None


def run_targets(db, dataset_id, named):
    held = image_ids(db, dataset_id)
    if named is None:
        # Every image: one left out of training is annotated too (user 2026-10-14: using for
        # training and annotating are apart).
        return held
    known = set(held)
    outside = [i for i in named if i not in known]
    if outside or len(set(named)) != len(named):
        raise invalid(
            "image_ids must be distinct images of the dataset", outside=outside
        )
    return list(named)


def references_of(db, dataset_id, revision=None, draft_write=None):
    """The images a plan (a version, a draft write; none: the plan now) takes as references."""
    return {
        r["image_id"]
        for r in plan_of(db, dataset_id, revision, draft_write).get("references") or []
    }


def named_references(db, dataset_id, image_ids, revision=None, draft_write=None):
    """The images named for a run that its plan takes as references, which it does not annotate
    (a worker's box naming them is refused, so it says what will run; definition 74)."""
    if not image_ids:
        return []
    examples = references_of(db, dataset_id, revision, draft_write)
    return [i for i in run_targets(db, dataset_id, image_ids) if i in examples]


def start_targets(db, dataset_id, image_ids, trial, revision=None, draft_write=None):
    """The images a run of a plan (a version or a draft write; none: the plan now) started with
    these inputs takes, the one place that says so (the decision's preview, its check and the
    run): never an image the plan takes as a reference, whose annotation is the reference
    (definition 38.1), named or not; a trial (the plan's samples) of no images: the first 3 of
    the order the dataset's sheets show, spread over it (definition 42.5). None left: refused."""
    from .sheets import dataset_order

    examples = references_of(db, dataset_id, revision, draft_write)
    unnamed_trial = trial and image_ids is None
    pool = (
        dataset_order(db, dataset_id)
        if unnamed_trial
        else run_targets(db, dataset_id, image_ids)
    )
    targets = [i for i in pool if i not in examples]
    if not targets:
        raise invalid(
            "No image to annotate: an image the plan takes as a reference is not annotated"
        )
    return targets[:3] if unnamed_trial else targets


def refuse_writing(db, dataset_id, targets):
    """Another decided run holds one of the images (it waits in the line or is making its
    result): a second run would replace that result unseen, so it is refused when it is decided
    (definition 18.13, user 2026-10-17). The person may stop the run that holds them."""
    held = writing(db, dataset_id, targets)
    if held:
        raise ApiError(
            409,
            "images_writing",
            "Another run holds some of the images (waiting or annotating); decide after it"
            " ends, or stop it",
            {"images": held},
        )


def run_limit(db, dataset_id, requirement_key, way, given=None):
    """A run's cost limit per image in US dollars, one rule for every run (definition 65, 84;
    user 2026-10-29, 10-30): the one its decision gives, else twice what one image cost by its
    way (usage.expected_cost, as a box's estimate says), else the settings'."""
    if given:
        return given
    expected = expected_cost(db, dataset_id, requirement_key, way)
    if expected is None:
        return str(read_settings(db)["run_budget_per_image_usd"])
    twice = 2 * expected["per_image_usd"]
    return str(twice.quantize(Decimal("0.01"), rounding=ROUND_UP))


def plan_to_run(db, dataset_id, draft_write=None, revision=None):
    """The plan a run or a box points at (drafts.plan_at: the one given, else the plan now); a
    run needs one."""
    at = plan_at(db, dataset_id, draft_write, revision)
    if not at:
        raise ApiError(422, "instruction_required", "Create an instruction first")
    return at


def recipe_for(db, dataset_id, revision, model, effort, shared_revision, actor):
    """The way of running of this plan version, model, effort and shared notes' version
    (definition 11.1, 18.15): one per content, made the first time it runs."""
    found = db.one(
        "SELECT id FROM recipes WHERE dataset_id=? AND instruction_revision=? AND model=?"
        " AND effort=? AND shared_revision=?",
        (dataset_id, revision, model, effort, shared_revision),
    )
    if found:
        return found["id"]
    recipe_id = new_id("rcp-")
    db.execute(
        "INSERT INTO recipes(id,dataset_id,instruction_revision,model,effort,shared_revision,"
        "created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (recipe_id, dataset_id, revision, model, effort, shared_revision, actor, now()),
    )
    return recipe_id
