# prevent __pycache__ folder from being annoying and appearing in library source
import sys
sys.dont_write_bytecode = True


import pytest
from williams.io.types import Gif

@pytest.fixture
def sample_gif():
    return Gif.from_url(
        "https://media.giphy.com/media/Ju7l5y9osyymQ/giphy.gif"
    )

def test_gif_url(sample_gif):
    assert len(sample_gif) > 0

def test_template_match(sample_gif):
    frame = sample_gif[0]
    template = frame[50:150, 50:150]

    _, score = sample_gif.best_match(template)

    assert score > 0.3