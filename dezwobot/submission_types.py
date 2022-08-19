import enum
import re


class SubmissionType(enum.IntFlag):
    no_paywall                  = enum.auto()
    always_paywall              = enum.auto()
    dynamic_paywall             = enum.auto()


def sueddeutsche(submission):
    if "dpa.urn-newsml-dpa" in submission.url:
        return SubmissionType.no_paywall
    return SubmissionType.dynamic_paywall


def welt(submission):
    if re.search("/plus\d+/", submission.url):
        return SubmissionType.always_paywall
    return SubmissionType.no_paywall


submission_types = {
    "faz.net":              SubmissionType.dynamic_paywall,
    "nzz.ch":               SubmissionType.dynamic_paywall,
    "spiegel.de":           SubmissionType.dynamic_paywall,
    "berliner-zeitung.de":  SubmissionType.dynamic_paywall,
    "stern.de":             SubmissionType.dynamic_paywall,
    "handelsblatt.com":     SubmissionType.dynamic_paywall,
    "wiwo.de":              SubmissionType.dynamic_paywall,
    "bild.de":              SubmissionType.dynamic_paywall,
    "reporterdesk.de":      SubmissionType.dynamic_paywall,
    "businessinsider.de":   SubmissionType.dynamic_paywall,
    "zeit.de":              SubmissionType.dynamic_paywall,

    "plus.tagesspiegel.de": SubmissionType.always_paywall,
    "cicero.de":            SubmissionType.always_paywall,

    "sueddeutsche.de":      sueddeutsche,
    "welt.de":              welt,
}
