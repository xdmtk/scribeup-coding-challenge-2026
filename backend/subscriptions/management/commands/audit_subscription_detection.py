from datetime import date
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from subscriptions.merchant_groups import group_transactions
from subscriptions.models import Transaction
from subscriptions.subscription_analysis import analyze_repeated_groups
from subscriptions.subscription_audit import build_report, render_json, render_text


class Command(BaseCommand):
    help = "Audit subscription detection for every user without modifying data."

    def add_arguments(self, parser):
        parser.add_argument("--user", type=int)
        parser.add_argument("--min-confidence", type=float, default=0)
        parser.add_argument("--classification", choices=("likely", "possible", "unlikely"))
        parser.add_argument("--borderline-only", action="store_true")
        parser.add_argument("--format", choices=("text", "json"), default="text")
        parser.add_argument("--output")
        parser.add_argument("--reference-date")
        parser.add_argument("--max-transactions-per-group", type=int)

    def handle(self, *args, **options):
        if not 0 <= options["min_confidence"] <= 1:
            raise CommandError("--min-confidence must be between 0 and 1")
        maximum = options["max_transactions_per_group"]
        if maximum is not None and maximum < 1:
            raise CommandError("--max-transactions-per-group must be at least 1")
        override = None
        if options["reference_date"]:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", options["reference_date"]):
                raise CommandError("Invalid --reference-date; expected YYYY-MM-DD")
            try:
                override = date.fromisoformat(options["reference_date"])
            except ValueError as error:
                raise CommandError("Invalid --reference-date; expected YYYY-MM-DD") from error

        queryset = Transaction.objects.all()
        if options["user"] is not None:
            queryset = queryset.filter(user_id=options["user"])
        transactions = list(queryset.order_by("user_id", "-charged_at", "id"))
        by_user = {}
        for transaction in transactions:
            by_user.setdefault(transaction.user_id, []).append(transaction)

        users = []
        for user_id, user_transactions in by_user.items():
            repeated, _ = group_transactions(user_transactions)
            reference = override or max(txn.charged_at.date() for txn in user_transactions)
            analysis = analyze_repeated_groups(repeated, reference)
            for category in ("likely_subscriptions", "possible_subscriptions", "unlikely_subscriptions"):
                analysis[category] = [item for item in analysis[category]
                                      if item["confidence_score"] >= options["min_confidence"] and
                                      (not options["classification"] or item["classification"] == options["classification"])]
            users.append({"user_id": user_id, **analysis})

        report = build_report(users, len(transactions))
        content = (render_json(report, options["borderline_only"]) if options["format"] == "json"
                   else render_text(report, options["borderline_only"], maximum))
        if options["output"]:
            path = Path(options["output"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            self.stdout.write(f"Subscription audit written to {path}")
        else:
            self.stdout.write(content, ending="")
