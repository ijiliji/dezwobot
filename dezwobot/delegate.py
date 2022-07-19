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

    "netzpolitik.org":      SubmissionType.no_paywall,
    "t-online.de":          SubmissionType.no_paywall,
    "taz.de":               SubmissionType.no_paywall,
    "derstandard.at":       SubmissionType.no_paywall,
    "orf.at":               SubmissionType.no_paywall,

    "rnd.de":               SubmissionType.only_static_paywall,

    "sueddeutsche.de":      SubmissionType.dynamic_paywall,
    "welt.de":              SubmissionType.dynamic_paywall,
}


class Delegate:
    DELETE_REGEX = re.compile(r"[^a-z0-9]*![^a-z]*delete[^a-z0-9]*")

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
        if submission.is_self or submission.is_reddit_media_domain:
            return
        st = self.submission_type(submission)
        if st == st.no_paywall:
            return

        body = [dedent("""\
            Danke für deine Einreichung! Falls der Artikel kostenpflichtig ist,
            antworte bitte mit einer Zusammenfassung des Artikels auf diesen
            Kommentar.""")]
        if st & st.dynamic_paywall:
            parts = ["Die eingereichte Seite ändert"]
            if st & st.dynamic_paywall_uncertain:
                parts.append("möglicherweise")
            parts.append(dedent("""\
                dynamisch, ob Artikel kostenpflichtig werden, stelle daher bitte
                mit einer Zusammenfassung oder einem Link zu einem Snapshot
                sicher, dass auch in diesem Falle mehr als nur die Überschrift
                diskutiert werden kann."""))
            body.append(" ".join(parts))
        elif st & st.only_static_paywall:
            body.append(dedent("""\
                Andernfalls antworte mit "!delete" auf diesen Kommentar, um ihn
                zu löschen. Du kannst deine Antwort anschließend auch selbst
                löschen."""))
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
                Zusammenfassung des Artikels bereitgestellt, danke dafür!""")
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
        exact_match = submission_types.get(submission.domain)
        domain = ".".join(tldextract.extract(submission.domain)[1:])
        domain_match = submission_types.get(domain)
        default = SubmissionType.dynamic_paywall | SubmissionType.dynamic_paywall_uncertain
        return exact_match or domain_match or default
