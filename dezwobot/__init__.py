import signal
import sys

from dezwobot.bot import Bot


def main():
    init = Bot.load
    if "new" in sys.argv:
        init = lambda x: Bot()
    skip_existing = True
    if "noskip" in sys.argv:
        skip_existing = False
    bot = init(skip_existing)
    signal.signal(signal.SIGINT, bot.signal_handler)
    signal.signal(signal.SIGTERM, bot.signal_handler)
    bot.run()
