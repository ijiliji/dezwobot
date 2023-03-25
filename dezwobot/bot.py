import dataclasses
import pickle
import re
import signal
import time
import traceback
from textwrap import dedent

import praw
import tldextract

from dezwobot import stream
from dezwobot.submission_types import SubmissionType, submission_types
from dezwobot.util import Queue, RemoveComment


@dataclasses.dataclass
class Nomination:
    nominee: praw.models.Comment
    nominator: praw.models.Comment
    category: str
    reason: str


class Bot:
    DELETE_REGEX = re.compile(r"(?i)\A[^a-z0-9]*![^a-z]*delete[^a-z0-9]*\Z")
    NOT_OP_BUT_OK_REGEX = re.compile(r"(?i)!notopbutok")
    ARTICLE_REQUEST_REGEX = re.compile(r"(?i)[^`]!(article[^a-z0-9]*request|request[^a-z0-9]*article)[^`]")
    NOMINATE_REGEX = re.compile(r"(?i)(?:^|\n\n)!nominate *(?P<category>\w*) *(?P<reason>(?:.|\n.)*)")
    # https://github.com/reddit-archive/reddit/blob/753b17407e9a9dca09558526805922de24133d53/r2/r2/models/subreddit.py#L114=
    SELF_REGEX = re.compile(r"(?i)\Aself\.[a-z0-9][a-z0-9_]{1,20}\Z")

    FURTHER_INFO = "[Weitere Informationen gibt es hier.](https://www.reddit.com/user/HerrZwoDezwo/comments/vz1jvf/)"

    def __init__(self):
        self.is_running = False

        self.reddit = praw.Reddit("dezwobot")
        self.me = self.reddit.user.me()
        self.admin = self.reddit.redditor("ijiliji")
        self.mods = list(map(
            self.reddit.redditor,
            "nivh_de kraal42 klausrade pstumpf ijiliji".split()))
        self.subreddit = self.reddit.subreddit("dezwo")

        # Workaround: Pickling UserSubreddit fails, remove it.
        for user in [self.me] + self.mods:
            user.subreddit = None

        self.queue = Queue(
            stream.MentionStream(self),
            stream.MessageStream(self),
            stream.SubmissionStream(self),
            stream.CommentStream(self),
            stream.SpamStream(self),
            )
        self.paywall_request = set()
        self.paywall_request_done = set()
        self.submissions = []
        self.comments = []
        self.nominations = []

    @classmethod
    def load(cls, skip_existing):
        with open("state.pkl", "rb") as f:
            bot = pickle.load(f)
        if skip_existing:
            for item in bot.queue:
                if isinstance(item, stream.Stream):
                    item.skip_before = time.time()
        return bot

    def save_state(self):
        self.dump_collected(force=True)
        with open("state.pkl", "wb") as f:
            pickle.dump(self, f)

    def signal_handler(self, sig, frame):
        self.is_running = False

    def run(self):
        self.is_running = True

        while self.is_running and self.queue:
            self.prune_paywall_requests()
            self.dump_collected()

            item = self.queue.get()

            wait_time = max(item.next - time.time(), 0)
            while self.is_running and wait_time > 1:
                wait_time -= 1
                time.sleep(1)
            if self.is_running:
                time.sleep(wait_time)

                try:
                    item.run()
                except Exception:
                    traceback.print_exc()

            try:
                self.queue.add(item)
            except Exception:
                traceback.print_exc()

        self.save_state()

    def process_submission(self, submission: praw.models.Submission):
        if submission in self.paywall_request or submission in self.paywall_request_done:
            return
        if submission.banned_by and submission.banned_by != "AutoModerator":
            return
        if submission.link_flair_template_id == "c3a93604-8237-11ed-aac0-8a01db1bde91":
            return

        self.submissions.append(submission)

        st = self.submission_type(submission)
        if st == st.no_paywall:
            return

        body = [dedent(f"""\
            Danke für deine Einreichung! Falls der Artikel kostenpflichtig ist,
            antworte bitte mit einer Zusammenfassung des Artikels auf diesen
            Kommentar, andernfalls antworte mit `!delete`.""")]
        if st == st.dynamic_paywall:
            body.append(self.snapshot_hint(submission))
        body.append(self.FURTHER_INFO)

        reply = submission.reply(body="\n\n".join(body))
        reply.mod.distinguish(sticky=True)
        self.paywall_request.add(reply)
        self.paywall_request.add(submission)

        self.queue.add(RemoveComment(reply))

    def process_comment(self, comment: praw.models.Comment):
        self.comments.append(comment)
        if comment.author == self.me:
            return
        matches = re.findall(self.NOMINATE_REGEX, comment.body)
        if matches:
            self.nominate(comment, matches)
        elif (
                isinstance(comment.parent(), praw.models.Comment)
                and comment.parent() in self.paywall_request):
            self.paywall_answered(comment)
        elif re.search(self.ARTICLE_REQUEST_REGEX, comment.body):
            self.article_request(comment)

    def paywall_answered(self, comment: praw.models.Comment):
        submission = comment.submission
        op = submission.author

        is_op_or_mod = comment.author in [op] + self.mods
        not_op_but_ok = re.search(self.NOT_OP_BUT_OK_REGEX, comment.body)

        if not is_op_or_mod and not not_op_but_ok:
            self.admin.message(
                subject=f"bot: reply by {comment.author} on {submission.title}",
                message=f"https://reddit.com{comment.permalink}\n\n{comment.body}")
            return

        if not is_op_or_mod and not_op_but_ok:
            self.print("!notopbutok", comment.author, op, submission.domain, submission.permalink)

        parent = comment.parent()
        parent.refresh()
        if self.article_provided(parent):
            return

        if parent.author == self.me:
            comment.mark_read()
        try:
            self.paywall_request.remove(parent)
            self.paywall_request.remove(submission)
        except KeyError:
            ...
        self.paywall_request_done.add(submission)
        if re.search(self.DELETE_REGEX, comment.body):
            parent.delete()
            comment.mod.remove()
            self.print("!delete", comment.author, op, submission.domain, submission.permalink)
        else:
            body = dedent(f"""\
                u/{comment.author} hat als Antwort auf diesen Kommentar eine
                Zusammenfassung des Artikels bereitgestellt, danke dafür!""")
            parent.edit(body=body)
            if parent.banned_by == self.me.name:
                parent.mod.approve()
                parent.mod.distinguish(sticky=True)

    def article_provided(self, comment):
        return "bereitgestellt" in comment.body

    def article_request(self, comment: praw.models.Comment):
        submission = comment.submission

        reply = None
        comments = [c for c in submission.comments if c.author == self.me]
        if comments:
            reply = comments[0]
            reply.refresh()
            if self.article_provided(reply):
                return
            if reply.banned_by == self.me.name:
                reply.mod.approve()
                reply.mod.distinguish(sticky=True)

        self.print("!article_request", comment.author, submission.domain, submission.permalink)

        body = [dedent(f"""\
            u/{comment.author} fragt nach einer Zusammenfassung oder einem
            Snapshot des Artikels, bzw. einem Platzhalter dafür.""")]
        if self.submission_type(submission) == SubmissionType.dynamic_paywall:
            body.append(self.snapshot_hint(comment.submission))
        body = "\n\n".join(body)
        if reply:
            reply.edit(body=body)
        else:
            reply = submission.reply(body=body)
            reply.mod.distinguish(sticky=True)
        self.paywall_request.add(submission)
        self.paywall_request.add(reply)

    def nominate(self, comment: praw.models.Comment, matches):
        parent = comment.parent()
        categories = "Argument Information Sprache".split()
        for category, reason in matches:
            selected = [x for x in categories if x.casefold().startswith(category.casefold())]
            self.nominations.append(Nomination(
                parent,
                comment,
                selected[0] if len(selected) == 1 else "Misc",
                reason.strip()))

        body = f"Nominierung erfolgreich. {self.FURTHER_INFO}"
        reply = comment.reply(body=body)
        reply.mod.distinguish()
        reply.mod.lock()

    def submission_type(self, submission):
        if re.search(self.SELF_REGEX, submission.domain):
            return SubmissionType.no_paywall
        exact_match = submission_types.get(submission.domain)
        domain = ".".join(tldextract.extract(submission.domain)[1:])
        domain_match = submission_types.get(domain)
        st = exact_match or domain_match or SubmissionType.no_paywall
        if callable(st):
            return st(submission)
        return st

    def prune_paywall_requests(self):
        week_ago = time.time() - 7*86400

        def f(c):
            try:
                return c.created_utc > week_ago
            except Exception:
                traceback.print_exc()
                return True

        self.paywall_request      = set(filter(f, self.paywall_request))
        self.paywall_request_done = set(filter(f, self.paywall_request_done))

    def dump_collected(self, force=False):
        try:
            self._dump_collected(force)
        except Exception:
            traceback.print_exc()

    def _dump_collected(self, force):
        v = 100
        if force and self.submissions or len(self.submissions) > v:
            with open(f"submissions-{int(time.time())}.pkl", "wb") as f:
                pickle.dump(self.submissions[:v], f)
                self.submissions = self.submissions[v:]
        if force and self.comments or len(self.comments) > v:
            with open(f"comments-{int(time.time())}.pkl", "wb") as f:
                pickle.dump(self.comments[:v], f)
                self.comments = self.comments[v:]

    def snapshot_hint(self, submission):
        submit = f"https://archive.ph/submit/?url={submission.url}"
        search = f"https://archive.ph/{submission.url}"
        return dedent(f"""\
            Falls der Artikel noch nicht kostenpflichtig ist, lässt sich ein
            Snapshot sehr einfach mit archive.ph erzeugen, nutze dazu
            [diesen Link]({submit}), um einen Snapshot im Hintergrund erstellen
            zu lassen, und antworte mit [diesem Link]({search}), welcher nach
            fertigen Snapshots sucht und damit sofort kommentiert werden kann -
            nutze dafür bspw. folgendes Markdown:

                [Snapshot]({search}).""")

    def print(self, *values):
        values = list(values)
        values[-1] = f"https://reddit.com{values[-1]}"
        print(":".join(map(str, values)))
