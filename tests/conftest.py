import pytest

from src import envgen


@pytest.fixture
def instance(tmp_path):
    return envgen.render_instance(tmp_path / "instances", envgen.new_instance_id(),
                                  "control", 0.5, "memo_a")
