import logging
import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ...consumer import Consumer, ConsumerError
from ...mail import MailFetcher, MailFetcherError

try:
    from inotifyrecursive import INotify, flags
except ImportError:
    INotify = flags = None


class Command(BaseCommand):
    """
    On every iteration of an infinite loop, consume what we can from the
    consumption directory, and fetch any mail available.
    """

    ORIGINAL_DOCS = os.path.join(settings.MEDIA_ROOT, "documents", "originals")
    THUMB_DOCS = os.path.join(settings.MEDIA_ROOT, "documents", "thumbnails")

    def __init__(self, *args, **kwargs):

        self.verbosity = 0
        self.logger = logging.getLogger(__name__)

        self.file_consumer = None
        self.mail_fetcher = None
        self.first_iteration = True

        BaseCommand.__init__(self, *args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "directory",
            default=settings.CONSUMPTION_DIR,
            nargs="?",
            help="The consumption directory."
        )
        parser.add_argument(
            "--loop-time",
            default=settings.CONSUMER_LOOP_TIME,
            type=int,
            help="Wait time between each loop (in seconds)."
        )
        parser.add_argument(
            "--mail-delta",
            default=10,
            type=int,
            help="Wait time between each mail fetch (in minutes)."
        )
        parser.add_argument(
            "--oneshot",
            action="store_true",
            help="Run only once."
        )
        parser.add_argument(
            "--no-inotify",
            action="store_true",
            help="Don't use inotify, even if it's available.",
            default=False
        )
        parser.add_argument(
            "--recursive",
            action="store_true",
            help="consume from subdirectories of the consumption directory.",
            default=False
        )

    def handle(self, *args, **options):

        self.verbosity = options["verbosity"]
        directory = options["directory"]
        loop_time = options["loop_time"]
        mail_delta = options["mail_delta"] * 60
        use_inotify = INotify is not None and options["no_inotify"] is False
        recursive = options["recursive"] or settings.CONSUMER_RECURSIVE

        try:
            self.file_consumer = Consumer(consume=directory)
            self.mail_fetcher = MailFetcher(consume=directory)
        except (ConsumerError, MailFetcherError) as e:
            raise CommandError(e)

        for d in (self.ORIGINAL_DOCS, self.THUMB_DOCS):
            os.makedirs(d, exist_ok=True)

        self.logger.info(
            "Starting{} document consumer at {}{}".format(
                " recursive" if recursive else "",
                directory,
                " with inotify" if use_inotify else ""
            )
        )

        if options["oneshot"]:
            self.loop_step(mail_delta)
        else:
            try:
                if use_inotify:
                    self.loop_inotify(mail_delta, recursive=recursive)
                else:
                    self.loop(loop_time, mail_delta, recursive=recursive)
            except KeyboardInterrupt:
                print("Exiting")

    def loop(self, loop_time, mail_delta, recursive=False):
        while True:
            start_time = time.time()
            if self.verbosity > 1:
                print(".", int(start_time))
            self.loop_step(mail_delta, start_time, recursive=recursive)
            # Sleep until the start of the next loop step
            time.sleep(max(0, start_time + loop_time - time.time()))

    def loop_step(self, mail_delta, time_now=None, recursive=False):

        # Occasionally fetch mail and store it to be consumed on the next loop
        # We fetch email when we first start up so that it is not necessary to
        # wait for 10 minutes after making changes to the config file.
        next_mail_time = self.mail_fetcher.last_checked + mail_delta
        if self.first_iteration or time_now > next_mail_time:
            self.first_iteration = False
            self.mail_fetcher.pull()

        self.file_consumer.consume_new_files(recursive=recursive)

    def loop_inotify(self, mail_delta, recursive=False):
        directory = self.file_consumer.consume
        inotify = INotify()
        inotify_flags = flags.CLOSE_WRITE | flags.MOVED_TO
        if recursive:
            inotify.add_watch_recursive(directory, inotify_flags)
        else:
            inotify.add_watch(directory, inotify_flags)

        # Run initial mail fetch and consume all currently existing documents
        self.loop_step(mail_delta, recursive=recursive)
        next_mail_time = self.mail_fetcher.last_checked + mail_delta

        while True:
            # Consume documents until next_mail_time
            while True:
                delta = next_mail_time - time.time()
                if delta > 0:
                    for event in inotify.read(timeout=delta):
                        if recursive:
                            path = inotify.get_path(event.wd)
                        else:
                            path = directory
                        file = os.path.join(path, event.name)
                        if os.path.isfile(file):
                            self.file_consumer.try_consume_file(file)
                        else:
                            self.logger.warning(
                                "Skipping %s as it is not a file",
                                file
                            )
                else:
                    break

            self.mail_fetcher.pull()
            next_mail_time = self.mail_fetcher.last_checked + mail_delta
