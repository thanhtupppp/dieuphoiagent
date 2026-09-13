from ui.log_streamer import LogStreamer


def test_log_streamer_push_and_subscribe():
    streamer = LogStreamer()
    received = []
    streamer.subscribe(lambda item: received.append(item))
    streamer.push("perplexity", "Found docs")
    assert len(received) == 1
    assert received[0]["source"] == "perplexity"
    assert received[0]["message"] == "Found docs"
