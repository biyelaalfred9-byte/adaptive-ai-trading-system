from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


def walk_forward_splits(data: Sequence[T], train_size: int, test_size: int):
    """Yield expanding-free rolling (train, test) slices in chronological order.

    Caller must supply chronologically ordered observations. No shuffling is used.
    """
    if train_size <= 0 or test_size <= 0:
        raise ValueError("train_size and test_size must be positive")
    start = 0
    while start + train_size + test_size <= len(data):
        train = data[start:start + train_size]
        test = data[start + train_size:start + train_size + test_size]
        yield train, test
        start += test_size
