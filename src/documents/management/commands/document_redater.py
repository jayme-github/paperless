import datetime
from dateutil.relativedelta import relativedelta

from django.core.management.base import BaseCommand, CommandError

from documents.models import Document


class Command(BaseCommand):

    help = """
        Set the created date for a sequence of documents.
        Usefull for documents with titles generated by Brother scanners that
        end with a counter.
        Given a common title prefix, the counter range (in form of Y-X) and a
        start_date (ISO format) this script sets the created date of each
        document found to the start_date, incremented by one (year, month or
        day; last argument) for every document.
        E.g. when run with "document_redater myprefix 1-4 1970-01-01 year" it
        will created date of myprefix_0001 to 1970-01-01, for myprefix_0002
        to 1971-01-01 and so forth.
        Non existing documents will be skipped and the date will not be
        incremented for them. Use "--dry-run" to see what would be done.
    """

    def add_arguments(self, parser):
        parser.add_argument("title")
        parser.add_argument("title_range")
        parser.add_argument("start_date", type=datetime.date.fromisoformat)
        parser.add_argument(
            "increment_by", default="month", choices=["year", "month", "day"]
        )
        parser.add_argument("--dry-run", action="store_true", default=False)

    def handle(self, *args, **options):
        title_start, title_end = options["title_range"].split("-")
        title_start = int(title_start)
        title_end = int(title_end)
        iterdate = options["start_date"]

        for x in range(title_start, title_end + 1):
            title = "{title}_{x:04}".format(title=options["title"], x=x)
            try:
                doc = Document.objects.get(title=title)
            except Document.DoesNotExist:
                print("No document with title: {title}".format(title=title))
                continue

            dd = doc.created.replace(
                year=iterdate.year, month=iterdate.month, day=iterdate.day
            )

            # Only write the doc if it needed changing
            if doc.created != dd:
                print(
                    "{title}: {from_date} -> {to_date}".format(
                        title=doc.title, from_date=doc.created, to_date=dd
                    )
                )
                if not options["dry_run"]:
                    doc.created = dd
                    doc.save()

            # Increment iterdate
            if options["increment_by"] == "year":
                iterdate += relativedelta(years=1)
            elif options["increment_by"] == "month":
                iterdate += relativedelta(months=1)
            elif options["increment_by"] == "day":
                iterdate += relativedelta(days=1)