import shutil

import pytest


def tf_binary():
    return shutil.which("tofu") or shutil.which("terraform")


@pytest.fixture
def tf_bin():
    b = tf_binary()
    if not b:
        pytest.skip("tofu/terraform not installed")
    return b


@pytest.fixture
def pulumi_bin():
    b = shutil.which("pulumi")
    if not b:
        pytest.skip("pulumi CLI not installed")
    return b
