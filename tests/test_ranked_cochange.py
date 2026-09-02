"""The ranked answer that replaces ROSE's silence, pinned at the unit.

`docs/audit.md` measured what the silence cost: `preflight` named 8% of the companions
E2's tasks turned on, and its co-change section said "History shows nothing that reliably
changes with this file" in 9 of 20 of them. That is the documented behaviour of the
threshold this project implements -- ROSE answers about a quarter of the time -- and
`cochange.rank_companions` is the TARMAQ-style answer for the other half.

**The properties tested here are the ones that make a ranked answer safe to show**: thin
evidence must sort below thick evidence rather than above it, agreement between two rules
must count for more than either alone, and nothing may be invented when history holds
nothing. `experiments/results/E5.md` carries the corpus-level numbers, including the
held-out repository that declined to confirm the F1 improvement.
"""
from __future__ import annotations

from codesextant import cochange


def _row(companion, support, changes):
    return {"companion": companion, "support": support, "changes": changes}


def test_thin_evidence_sorts_below_thick_evidence():
    """Raw confidence puts one-of-one at 1.00, above nineteen-of-twenty at 0.95.

    That inversion is what `min_support` was defending against, and the defence cost an
    answer whenever nothing cleared the floor. A Wilson lower bound makes the same
    correction continuously, so the coincidence is ranked last instead of ranked first.
    """
    ranked = cochange.rank_companions(
        [_row("coincidence", 1, 1), _row("reliable", 19, 20)], limit=5)

    assert [row["companion"] for row in ranked] == ["reliable", "coincidence"]
    assert ranked[0]["score"] > ranked[1]["score"] * 3


def test_two_rules_agreeing_beat_either_one_alone():
    """The MSR-2016 result, at the unit: several rules naming the same file are more
    evidence than one. Noisy-OR is the aggregator, so agreement accumulates."""
    alone = cochange.rank_companions([_row("shared", 3, 6)], limit=5)
    agreed = cochange.rank_companions(
        [_row("shared", 3, 6), _row("shared", 3, 6)], limit=5)

    assert agreed[0]["score"] > alone[0]["score"]
    assert agreed[0]["score"] < 1.0, "aggregation must stay a probability"
    assert len(agreed) == 1, "one companion, however many rules named it"


def test_where_agreement_stops_being_worth_more_than_strength():
    """Aggregation is worth something and it is worth a bounded something, so the bound
    is what gets pinned rather than a hopeful direction.

    Two rules at 4-of-10 aggregate to 0.308. That beats a single 5-of-10 rule at 0.237
    and **loses** to a single 6-of-10 at 0.313. Written after asserting the general claim
    and watching it fail: agreement between two middling rules does not outweigh one
    clearly stronger rule, and a reader deciding whether to trust the top of this list
    should be able to find that here rather than derive it.
    """
    beats_weaker = cochange.rank_companions(
        [_row("agreed", 4, 10), _row("agreed", 4, 10), _row("once", 5, 10)], limit=5)
    assert beats_weaker[0]["companion"] == "agreed"

    loses_to_stronger = cochange.rank_companions(
        [_row("agreed", 4, 10), _row("agreed", 4, 10), _row("once", 6, 10)], limit=5)
    assert loses_to_stronger[0]["companion"] == "once"


def test_history_with_nothing_in_it_is_still_nothing():
    """The failure mode worse than silence is an answer that is never empty, because a
    list that always says something is a list that never means anything."""
    assert cochange.rank_companions([], limit=5) == []
    assert cochange.rank_companions([_row("never", 0, 4)], limit=5) == []


def test_the_query_file_is_never_its_own_companion():
    assert cochange.rank_companions(
        [_row("self.py", 9, 9), _row("other.py", 2, 9)],
        limit=5, exclude={"self.py"}) == [
            row for row in cochange.rank_companions(
                [_row("other.py", 2, 9)], limit=5)]


def test_the_limit_is_a_limit():
    rows = [_row(f"f{n}.py", 5, 10) for n in range(9)]
    assert len(cochange.rank_companions(rows, limit=3)) == 3


def test_a_ranked_row_carries_the_same_keys_a_thresholded_rule_does():
    """Found by the renderer test rather than by reading: `_merge_cochange` reads
    `confidence`, and the first version of these rows did not have it. A ranked answer
    has to be a drop-in for a thresholded one everywhere downstream."""
    ranked = cochange.rank_companions([_row("companion.py", 3, 4)], limit=5)

    assert set(ranked[0]) >= {"companion", "support", "changes", "confidence", "score"}
    assert ranked[0]["confidence"] == 0.75


def test_the_ranked_fallback_can_be_turned_off_on_its_own(monkeypatch):
    """`CODESEXTANT_COCHANGE_RANK_LIMIT=0` cannot do it -- `_env_int` returns the default
    for anything not positive, which is the right contract for `max_commits` and would be
    a trap here -- and disabling co-change entirely takes the thresholded answer too."""
    assert cochange.ranked_enabled() is True
    monkeypatch.setenv("CODESEXTANT_COCHANGE_RANKED_DISABLED", "1")
    assert cochange.ranked_enabled() is False
    assert cochange.enabled() is True, "the thresholded half stays"
