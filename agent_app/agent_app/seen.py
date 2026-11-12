"""What an AI is told of the images it is shown and of the data it reads (definition 29.1): a
view's number, its image, its size, whether it is shrunk (32.7) and what is drawn on it in its
own pixels; never where it was cut from or its scale. Coordinates reach an AI only this way, so
it measures and answers in the pixels of an image it saw and the server turns them into
original pixels (coordinates.py).
"""

from .coordinates import shrunk, to_view_geometry

# What a drawn object keeps beside its geometry (a result's annotations, a reference's among them:
# definitions 32.5, 38.1).
KEPT = ("id", "label", "attributes", "parent_id", "number")


def seen(frame, objects=()):
    """The view as the AI is told it; objects: what is drawn on it, in original pixels."""
    return {
        "view_id": frame["view_id"],
        "image_id": frame["image_id"],
        "output_size": frame["output_size"],
        "shrunk": shrunk(frame),
        "drawn": [
            {
                **{k: o[k] for k in KEPT if k in o},
                "geometry": to_view_geometry(o["geometry"], frame),
            }
            for o in objects
            if o.get("geometry")
        ],
    }


def without_geometry(data):
    """A tool's data with every geometry taken out (original pixels are never shown)."""
    if isinstance(data, dict):
        return {k: without_geometry(v) for k, v in data.items() if k != "geometry"}
    if isinstance(data, list):
        return [without_geometry(v) for v in data]
    return data
