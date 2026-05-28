"""Unit tests for pure helper functions in models.py."""

import os
import sys

import pytest

base_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(base_path))

from models import age_group_for  # noqa: E402


@pytest.mark.parametrize(
    "age, expected",
    [
        # too_young boundary
        (0,   "too_young"),
        (3,   "too_young"),
        # dragon
        (4,   "dragon"),
        (7,   "dragon"),
        # tiger
        (8,   "tiger"),
        (9,   "tiger"),
        # youth
        (10,  "youth"),
        (11,  "youth"),
        # cadet
        (12,  "cadet"),
        (14,  "cadet"),
        # junior
        (15,  "junior"),
        (16,  "junior"),
        # senior boundaries
        (17,  "senior"),
        (32,  "senior"),
        # ultra boundaries
        (33,  "ultra"),
        (99,  "ultra"),
        # too_old (outside map)
        (100, "too_old"),
        (-1,  "too_old"),
        # string input coercion
        ("17", "senior"),
    ],
)
def test_age_group_for(age, expected):
    assert age_group_for(age) == expected
