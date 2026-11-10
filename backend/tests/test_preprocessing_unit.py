"""Focused preprocessing unit tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services.preprocessing import TopKFeatures, _benign_labels


def test_topk_selector_clamps_requested_k_to_available_features():
    rng = np.random.default_rng(3)
    features = rng.normal(size=(40, 8))
    labels = np.array([0, 1] * 20)
    selector = TopKFeatures(k=50).fit(features, labels)
    assert selector.transform(features).shape == (40, 8)
    assert selector.get_support().sum() == 8

    selector = TopKFeatures(k=3).fit(features, labels)
    assert selector.transform(features).shape == (40, 3)
    assert selector.get_support().sum() == 3


def test_benign_label_resolution_and_validation():
    series = pd.Series(["Normal", "flood", "BENIGN", "port_scan"])
    assert set(_benign_labels(series, None)) == {"Normal", "BENIGN"}
    assert _benign_labels(pd.Series(["0", "1", "1"]), None) == ["0"]
    with pytest.raises(ValueError):
        _benign_labels(series, ["does-not-exist"])
