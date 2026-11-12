from agent_app.instructions import requirement_key


def label(**changes):
    base = {
        "id": "lbl-box",
        "name": "box",
        "shape": "bbox",
        "parent": None,
        "description": "a box",
        "scope": "image",
        "attributes": [
            {
                "name": "lot",
                "type": "text",
                "choices": None,
                "description": "",
                "scope": "image",
            },
            {
                "name": "kind",
                "type": "choice",
                "choices": ["b", "a"],
                "description": "",
                "scope": "image",
            },
        ],
    }
    return {**base, **changes}


def test_same_requirement_ignores_wording_order_and_empty_choices():
    a = [
        label(),
        {
            "id": "lbl-lid",
            "name": "lid",
            "shape": "polygon",
            "parent": "box",
            "attributes": [],
        },
    ]
    b = [
        {
            "id": "lbl-lid",
            "name": "lid",
            "shape": "polygon",
            "parent": "box",
            "attributes": [],
            "description": "x",
        },
        label(
            description="something else",
            attributes=[
                {
                    "name": "kind",
                    "type": "choice",
                    "choices": ["a", "b"],
                    "description": "y",
                },
                {"name": "lot", "type": "text", "choices": [], "description": "z"},
            ],
        ),
    ]
    assert requirement_key(a) == requirement_key(b)


def test_structure_changes_make_another_requirement():
    base = requirement_key([label()])
    assert requirement_key([label(shape="polygon")]) != base
    assert requirement_key([label(scope="group")]) != base
    # The attributes are not the requirement (definition 85.17): a value missing is counted.
    other = label()
    other["attributes"] = [
        {**other["attributes"][0], "type": "number"},
        other["attributes"][1],
    ]
    assert requirement_key([other]) == base
    assert requirement_key([label(attributes=[])]) == base


def test_a_label_is_its_id_not_its_name():
    # Definition 23.3 (issue #4 F-01): renamed, the same label; another label of the same
    # name, another requirement.
    base = requirement_key([label()])
    assert requirement_key([label(name="crate")]) == base
    assert requirement_key([label(id="lbl-other")]) != base
