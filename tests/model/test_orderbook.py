from tplus.model.orderbook import OrderBook, OrderBookDiff


def test_depth_diff_is_not_a_reset_unless_told():
    diff = OrderBookDiff.model_validate({"bids": [["98", "1"]], "asks": [], "sequence_number": 4})

    assert not diff.reset


def test_depth_diff_reset_carries_no_levels():
    diff = OrderBookDiff(bids=[], asks=[], sequence_number=5, reset=True)

    assert diff.reset
    assert diff.bids == [] and diff.asks == []


def test_depth_is_trustworthy_unless_told_stale():
    assert not OrderBook(asks=[], bids=[], sequence_number=1).stale
    assert not OrderBookDiff(bids=[[98.0, 1.0]], asks=[], sequence_number=4).stale


def test_depth_reads_the_stale_flag_mds_serves():
    snapshot = OrderBook.model_validate(
        {"asks": [], "bids": [], "sequence_number": 1, "stale": True}
    )
    diff = OrderBookDiff.model_validate(
        {"bids": [], "asks": [], "sequence_number": 2, "stale": True}
    )

    assert snapshot.stale
    assert diff.stale
