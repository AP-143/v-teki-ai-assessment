import joblib
import pytest

from fraud_risk.features import FEATURES
from fraud_risk.generate_data import generate, write_tables
from fraud_risk.privacy import KEY_ENV
from fraud_risk.train import RuleBaseline

TEST_KEY = "test-key-not-a-real-secret"


@pytest.fixture
def raw_tables():
    """A small synthetic dataset, regenerated per test so tests cannot affect each other."""
    return generate(n_customers=300, seed=1)


@pytest.fixture
def key():
    return TEST_KEY.encode()


@pytest.fixture
def rules_bundle():
    """A model bundle shaped like train.py's output; the rule baseline needs no training."""
    return {"model": RuleBaseline(), "version": "rules-v1", "features": FEATURES}


@pytest.fixture
def data_dir(tmp_path, raw_tables, monkeypatch):
    """Raw CSVs on disk plus the pseudonym key in the environment, as a reviewer would run it."""
    write_tables(raw_tables, tmp_path / "raw")
    monkeypatch.setenv(KEY_ENV, TEST_KEY)
    return tmp_path / "raw"


@pytest.fixture
def model_path(tmp_path, rules_bundle):
    path = tmp_path / "model.joblib"
    joblib.dump(rules_bundle, path)
    return path
