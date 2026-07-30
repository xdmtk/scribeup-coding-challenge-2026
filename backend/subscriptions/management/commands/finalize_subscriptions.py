from django.core.management.base import BaseCommand, CommandError

from subscriptions.assessments import get_or_refresh_user_assessments
from subscriptions.models import Transaction


class Command(BaseCommand):
    help = "Create or refresh persisted finalized subscription assessments"

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument("--user", type=int)
        target.add_argument("--all-users", action="store_true")
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--no-llm", action="store_true")
        parser.add_argument("--only-stale", action="store_true",
                            help="Explicitly retain the default stale-only behavior")

    def handle(self, *args, **options):
        users = ([options["user"]] if options["user"] is not None else list(
            Transaction.objects.values_list("user_id", flat=True).distinct().order_by("user_id")
        ))
        totals = {key: 0 for key in ("merchant_groups_processed", "cached_assessments_reused",
                  "stale_assessments_refreshed", "heuristic_only_finalizations",
                  "llm_reviews_attempted", "llm_reviews_completed", "llm_reviews_failed")}
        classifications = {"subscription": 0, "not_subscription": 0, "uncertain": 0}
        processed = 0
        for user_id in users:
            result = get_or_refresh_user_assessments(
                user_id, allow_llm=not options["no_llm"], force=options["force"])
            if result is None:
                if options["user"] is not None:
                    raise CommandError(f"User {user_id} not found")
                continue
            processed += 1
            for key in totals:
                totals[key] += getattr(result.stats, key)
            for row in result.assessments:
                classifications[row.final_classification] += 1
                if options["verbosity"] >= 2:
                    self.stdout.write(
                        f"user={user_id} merchant={row.normalized_merchant} "
                        f"heuristic={row.heuristic_classification} final={row.final_classification} "
                        f"source={row.assessment_source} llm_status={row.llm_review_status}"
                    )
        self.stdout.write(f"users processed: {processed}")
        for key, value in totals.items():
            self.stdout.write(f"{key.replace('_', ' ')}: {value}")
        for key, value in classifications.items():
            self.stdout.write(f"{key.replace('_', '-')} results: {value}")
