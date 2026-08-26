import logging
from pathlib import Path

import pytest

from plym.config.site import REMOVED_KEYS, SiteConfig, load_site_config
from plym.render.cache_policy import CachePolicy


def test_http_cache_is_no_longer_a_setting() -> None:
    assert "http_cache" not in SiteConfig.model_fields
    assert "http_cache" in REMOVED_KEYS


def test_an_existing_config_still_loads_and_says_what_happened(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "website: plym.local\n"
        "blog_home: plym.local\n"
        "http_cache:\n"
        "  enabled: true\n"
        "  max_age: 1234\n"
        "typo_key: 1\n",
        encoding="utf-8",
    )

    load_site_config.cache_clear()
    try:
        with caplog.at_level(logging.WARNING, logger="plym.config"):
            site = load_site_config(config)
    finally:
        load_site_config.cache_clear()

    assert site.name == "Plym"
    messages = [record.getMessage() for record in caplog.records]
    assert any("http_cache" in m and "no longer used" in m for m in messages), messages
    assert any("typo_key" in m and "not a plym setting" in m for m in messages), messages


def test_the_defaults_the_removed_block_used_to_carry_are_preserved() -> None:
    # http_cache defaulted to max_age 300 for posts and index_max_age 60 for the
    # dynamic routes. Anyone who never touched the block sees no change.
    assert CachePolicy.PAGE.startswith("public, max-age=300")
    assert CachePolicy.MARKDOWN == "public, max-age=300"
    assert CachePolicy.LISTING == "public, max-age=60"


def test_every_policy_is_a_well_formed_cache_control() -> None:
    for policy in CachePolicy:
        directives = [part.strip() for part in policy.split(",")]
        assert directives[0] in ("public", "private"), policy
        assert any(d.startswith("max-age=") for d in directives), policy
