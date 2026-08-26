from plym.config.merge import deep_merge


def test_overlay_wins_on_leaf_conflict() -> None:
    base = {"fonts": {"heading": "Inter", "body": "Merriweather"}}
    overlay = {"fonts": {"heading": "Roboto"}}
    result = deep_merge(base, overlay)
    assert result["fonts"]["heading"] == "Roboto"
    assert result["fonts"]["body"] == "Merriweather"


def test_overlay_adds_new_keys() -> None:
    base = {"a": 1}
    overlay = {"b": 2}
    assert deep_merge(base, overlay) == {"a": 1, "b": 2}


def test_lists_replace_not_merge() -> None:
    base = {"robots": {"disallow_paths": ["/api/"]}}
    overlay = {"robots": {"disallow_paths": ["/api/", "/private/"]}}
    result = deep_merge(base, overlay)
    assert result["robots"]["disallow_paths"] == ["/api/", "/private/"]


def test_does_not_mutate_inputs() -> None:
    base = {"x": {"y": 1}}
    overlay = {"x": {"z": 2}}
    deep_merge(base, overlay)
    assert base == {"x": {"y": 1}}
    assert overlay == {"x": {"z": 2}}


def test_overlay_dict_replaces_non_dict_in_base() -> None:
    base = {"x": "string"}
    overlay = {"x": {"nested": 1}}
    assert deep_merge(base, overlay) == {"x": {"nested": 1}}


def test_empty_overlay_returns_base_copy() -> None:
    base = {"a": {"b": 1}}
    result = deep_merge(base, {})
    assert result == {"a": {"b": 1}}
    assert result is not base


def test_empty_base_returns_overlay_copy() -> None:
    overlay = {"a": {"b": 1}}
    result = deep_merge({}, overlay)
    assert result == {"a": {"b": 1}}
