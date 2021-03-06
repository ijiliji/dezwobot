import enum
import re
import traceback
from textwrap import dedent
from typing import Union

import praw
import tldextract

class SubmissionType(enum.IntFlag):
    no_paywall                  = enum.auto()
    only_static_paywall         = enum.auto()
    dynamic_paywall             = enum.auto()
    dynamic_paywall_uncertain   = enum.auto()


submission_types = {
    "reddit.com":           SubmissionType.no_paywall,
    "redd.it":              SubmissionType.no_paywall,
    "imgur.com":            SubmissionType.no_paywall,
    "youtube.com":          SubmissionType.no_paywall,
    "youtu.be":             SubmissionType.no_paywall,

    "arte.tv":              SubmissionType.no_paywall,
    "br.de":                SubmissionType.no_paywall,
    "deutschlandfunk.de":   SubmissionType.no_paywall,
    "dw.com":               SubmissionType.no_paywall,
    "hessenschau.de":       SubmissionType.no_paywall,
    "mdr.de":               SubmissionType.no_paywall,
    "ndr.de":               SubmissionType.no_paywall,
    "swr.de":               SubmissionType.no_paywall,
    "tagesschau.de":        SubmissionType.no_paywall,
    "wdr.de":               SubmissionType.no_paywall,
    "zdf.de":               SubmissionType.no_paywall,
    "funk.net":             SubmissionType.no_paywall,

    "netzpolitik.org":      SubmissionType.no_paywall,
    "t-online.de":          SubmissionType.no_paywall,
    "taz.de":               SubmissionType.no_paywall,
    "derstandard.at":       SubmissionType.no_paywall,
    "orf.at":               SubmissionType.no_paywall,
    "theguardian.com":      SubmissionType.no_paywall,

    "rnd.de":               SubmissionType.only_static_paywall,

    "sueddeutsche.de":      SubmissionType.dynamic_paywall,
    "welt.de":              SubmissionType.dynamic_paywall,
}


class Delegate:
    DELETE_REGEX = re.compile(r"[^a-z0-9]*![^a-z]*delete[^a-z0-9]*")

    # https://github.com/reddit-archive/reddit/blob/753b17407e9a9dca09558526805922de24133d53/r2/r2/models/subreddit.py#L114=
    SELF_REGEX = re.compile(r"self\.[A-Za-z0-9][A-Za-z0-9_]{2,20}")

    def __init__(self, reddit, **kwargs):
        self.reddit = reddit

        if kwargs:
            self.__dict__.update(kwargs)
        else:
            self.admin = reddit.redditor("ijiliji")

    def new(self):
        return Delegate(**self.__dict__)

    def shutdown(self, failure=False):
        ...

    def process(self, data):
        try:
            if isinstance(data, praw.models.Submission):
                self.process_submission(data)
            elif isinstance(data, praw.models.Comment):
                self.process_comment_reply(data)
            elif isinstance(data, praw.models.Message):
                self.process_message(data)
            else:
                raise TypeError(data)
        except Exception:
            traceback.print_exc()

    def process_submission(self, submission: praw.models.Submission):
        st = self.submission_type(submission)
        if st == st.no_paywall:
            return

        body = [dedent("""\
            Danke f??r deine Einreichung! Falls der Artikel kostenpflichtig ist,
            antworte bitte mit einer Zusammenfassung des Artikels auf diesen
            Kommentar.""")]
        if st & st.dynamic_paywall:
            parts = ["Die eingereichte Seite ??ndert"]
            if st & st.dynamic_paywall_uncertain:
                parts.append("m??glicherweise")
            parts.append(dedent("""\
                dynamisch, ob Artikel kostenpflichtig werden, stelle daher bitte
                mit einer Zusammenfassung oder einem Link zu einem Snapshot
                sicher, dass auch in diesem Falle mehr als nur die ??berschrift
                diskutiert werden kann."""))
            body.append(" ".join(parts))
        body.append(dedent("""\
            Andernfalls antworte mit "!delete" auf diesen Kommentar, um ihn zu
            l??schen. Du kannst deine Antwort anschlie??end auch selbst
            l??schen."""))
        body.append("[Weitere Informationen gibt es hier.](https://www.reddit.com/user/HerrZwoDezwo/comments/vz1jvf/)")

        comment = submission.reply(body="\n\n".join(body))
        comment.mod.distinguish(sticky=True)

    def process_comment_reply(self, comment: praw.models.Comment):
        submission = comment.submission
        op = submission.author
        if comment.author != op:
            return

        parent = comment.parent()
        parent.refresh()
        cid = comment.id
        if any(c for c in parent.replies if c.id != cid and c.author == op):
            return

        comment.mark_read()

        if re.fullmatch(self.DELETE_REGEX, comment.body):
            parent.delete()
            comment.mod.remove()
            print(f"!delete:{submission.domain}:https://reddit.com{submission.permalink}")
        else:
            body = dedent(f"""\
                u/{comment.author} hat als Antwort auf diesen Kommentar eine
                Zusammenfassung des Artikels bereitgestellt, danke daf??r!""")
            parent.edit(body=body)

    def process_message(self, message: praw.models.Message):
        message.mark_read()

        body = dedent(f"""\
            https://reddit.com/u/{message.author}

            https://reddit.com/message/messages/{message.id}

            {message.subject}

            ---

            {message.body}""")
        self.admin.message(subject="bot message", message=body)

    def submission_type(self, submission):
        if re.fullmatch(self.SELF_REGEX, submission.domain):
            return SubmissionType.no_paywall
        exact_match = submission_types.get(submission.domain)
        domain = ".".join(tldextract.extract(submission.domain)[1:])
        domain_match = submission_types.get(domain)
        default = SubmissionType.dynamic_paywall | SubmissionType.dynamic_paywall_uncertain
        return exact_match or domain_match or default
