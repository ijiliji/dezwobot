import time
import traceback

import praw

from dezwobot.backoff import ConstantBackoff, ExponentialBackoff
from dezwobot.util import Queueable


class Stream(Queueable):
    def __init__(self, bot, backoff, fetch):
        super().__init__()

        self.bot = bot
        self.skip_before = time.time()
        self.backoff = backoff
        self._fetch = fetch
        self.seen = praw.models.util.BoundedSet(1000)

    def run(self):
        try:
            items = self._run()
        except Exception:
            items = []
            traceback.print_exc()

        if items:
            for item in items:
                try:
                    self.process(item)
                except Exception:
                    traceback.print_exc()
            self.backoff.reset()
        else:
            self.backoff.increment()

        self.next = time.time() + self.backoff.value()

        return True

    def _run(self):
        items = list(self._fetch(limit=1))

        if (
                not items
                or items[0].fullname in self.seen
                or items[0].created_utc < self.skip_before):
            return []

        after = items[0].fullname
        while True:
            returned = list(self._fetch(limit=100, params={"after": after}))
            if not returned:
                break
            new = [
                c for c in returned
                if c.fullname not in self.seen and c.created_utc >= self.skip_before]
            items.extend(new)
            if len(new) != len(returned):
                break
            after = min(items, key=lambda c: c.created_utc).fullname

        for item in items:
            self.seen.add(item.fullname)
        items.sort(key=lambda c: c.created_utc)

        return items

class MentionStream(Stream):
    def  __init__(self, bot):
        super().__init__(
            bot,
            ConstantBackoff(15*60),
            bot.reddit.inbox.mentions)

    def process(self, item):
        self.bot.admin.message(
            subject=f"bot: mentioned by {item.author} on {item.submission.title}[:100]",
            message=f"https://reddit.com{item.context}  \n{item.submission.title}\n\n{item.body}")
        item.mark_read()


class MessageStream(Stream):
    def  __init__(self, bot):
        super().__init__(
            bot,
            ConstantBackoff(15*60),
            bot.reddit.inbox.messages)

    def process(self, item):
        if item.author == self.bot.me:
            item.mark_read()
            return
        self.bot.admin.message(
            subject=f"bot: msg by {item.author}: {item.subject}"[:100],
            message=f"https://reddit.com/message/messages/{item.id}  \n{item.subject}\n\n{item.body}")
        item.mark_read()


class SubmissionStream(Stream):
    def  __init__(self, bot):
        super().__init__(
            bot,
            ConstantBackoff(5, 5, 5, 10, 10, 15, 25),
            bot.subreddit.new)

    def process(self, item):
        self.bot.process_submission(item)


class CommentStream(Stream):
    def  __init__(self, bot):
        super().__init__(
            bot,
            ExponentialBackoff(base=2, min_time=16, max_time=60),
            bot.subreddit.comments)

    def process(self, item):
        self.bot.process_comment(item)


class SpamStream(Stream):
    def  __init__(self, bot):
        super().__init__(
            bot,
            ConstantBackoff(10, 10, 10, 10, 10, 120),
            bot.subreddit.mod.spam)

    def process(self, item):
        if isinstance(item, praw.models.Submission):
            self.bot.process_submission(item)
