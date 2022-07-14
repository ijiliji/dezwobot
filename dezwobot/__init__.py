import importlib
import random
import signal
import time
import traceback
from datetime import datetime

import praw

from dezwobot import delegate


class ExponentialBackoff:
    """Default values based on praw.models.util.ExponentialCounter."""

    def __init__(self, base=1.1, max_time=16, max_jitter_fraction=0.03125):
        self.base = base
        self.max = max_time
        self.jitter_factor = 2 * max_jitter_fraction
        self.counter = 1

    def increment(self):
        self.counter += 1

    def reset(self):
        self.counter = 1

    def value(self):
        value = min(self.base**self.counter, self.max)
        max_jitter = value * self.jitter_factor
        return value + random.random() * max_jitter - max_jitter / 2


class Bot:
    def __init__(self):
        self.running = True
        self.reload_delegate = False
        self.reddit = praw.Reddit("dezwobot")
        self.delegate = delegate.Delegate(self.reddit)

    def signal_handler(self, sig, frame):
        if sig == signal.SIGUSR1:
            self.reload_delegate = True
        else:
            self.running = False

    def run(self):
        stream_kwargs = {
            "pause_after": 0,
            "skip_existing": True}
        subreddit = self.reddit.subreddit("dezwo")
        submission_stream = subreddit.stream.submissions(**stream_kwargs)
        inbox_stream = self.reddit.inbox.stream(**stream_kwargs)
        backoff = ExponentialBackoff()

        while self.running:
            if self.reload_delegate:
                try:
                    importlib.reload(delegate)
                    self.delegate = self.delegate.new()
                    self.reload_delegate = False
                except Exception:
                    traceback.print_exc()

            for stream in (submission_stream, inbox_stream):
                for data in stream:
                    if data is None:
                        backoff.increment()
                        break
                    backoff.reset()
                    self.delegate.process(data)

            time.sleep(backoff.value())

    def start(self):
        while self.running:
            try:
                self.run()
            except praw.exceptions.PRAWException:
                traceback.print_exc()
            except Exception:
                traceback.print_exc()
                self.delegate.shutdown(failure=True)
                return
        self.delegate.shutdown()


def main():
    bot = Bot()
    signal.signal(signal.SIGINT, bot.signal_handler)
    signal.signal(signal.SIGTERM, bot.signal_handler)
    signal.signal(signal.SIGUSR1, bot.signal_handler)
    bot.start()
