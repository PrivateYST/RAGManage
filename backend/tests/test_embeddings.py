import math

import pytest

from app.rag.models import validate_embeddings


@pytest.mark.parametrize(
    "value", [None, [], [[1]], [[0, 0]], [[math.nan, 1]], [[math.inf, 1]], [[True, 1]], [["1", 1]]]
)
def test_bad_embedding_is_rejected(value: object) -> None:
    with pytest.raises(ValueError):
        validate_embeddings(value, 1, 2)


def test_normalization() -> None:
    assert validate_embeddings([[3, 4]], 1, 2) == [[0.6, 0.8]]
