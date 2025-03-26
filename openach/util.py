"""Utility functions for working with iterators and collections."""

import itertools


def partition(pred, iterable):
    """Use a predicate to partition entries into false entries and true entries."""
    # https://stackoverflow.com/questions/8793772/how-to-split-a-sequence-according-to-a-predicate
    # NOTE: this might iterate over the collection twice
    # NOTE: need to use filter(s) here because we're lazily dealing with iterators
    it1, it2 = itertools.tee(iterable)
    return (
        itertools.filterfalse(pred, it1),
        filter(pred, it2),
    )  # pylint: disable=bad-builtin


def first_occurrences(iterable):
    """Return list where subsequent occurrences of repeat elements have been removed."""
    added = set()
    result = []
    for elt in iterable:
        if elt not in added:
            result.append(elt)
            added.add(elt)
    return result
