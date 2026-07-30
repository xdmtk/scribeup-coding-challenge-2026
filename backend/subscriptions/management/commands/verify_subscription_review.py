from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from subscriptions.assessments import (get_or_refresh_user_assessments,
    transaction_fingerprint, validate_cached_assessment)
from subscriptions.finalization import requires_llm_review
from subscriptions.merchant_groups import group_transactions
from subscriptions.models import SubscriptionAssessment, Transaction
from subscriptions.subscription_analysis import analyze_merchant_group
from subscriptions.versions import FINALIZATION_VERSION, HEURISTIC_VERSION, LLM_PROMPT_VERSION


def yes(value):
    return "yes" if value else "no"


class Command(BaseCommand):
    help = "Safely inspect semantic-review configuration, routing, and cache validity"

    def add_arguments(self, parser):
        parser.add_argument("--user", type=int, required=True)
        parser.add_argument("--merchant")
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--no-call", action="store_true")

    def handle(self, *args, **options):
        user_id = options["user"]
        txns = list(Transaction.objects.filter(user_id=user_id).order_by("charged_at", "id"))
        if not txns:
            raise CommandError(f"User {user_id} not found")
        groups, _ = group_transactions(txns)
        if options["merchant"]:
            needle = options["merchant"].casefold().strip()
            matches = [group for group in groups if needle in {
                group["display_merchant"].casefold(), group["normalized_merchant"].casefold(),
                *(variant.casefold() for variant in group["merchant_variants"])}]
            if not matches:
                raise CommandError(f'No repeated merchant matches "{options["merchant"]}"')
            if len(matches) > 1:
                names = ", ".join(group["display_merchant"] for group in matches)
                raise CommandError(f"Multiple merchant groups matched: {names}. Use a more specific value.")
            groups = matches

        self.stdout.write("Configuration")
        self.stdout.write(f"OpenAI review enabled: {yes(settings.OPENAI_SUBSCRIPTION_REVIEW_ENABLED)}")
        self.stdout.write(f"API key configured: {yes(bool(settings.OPENAI_API_KEY))}")
        self.stdout.write(f"Model: {settings.OPENAI_MODEL}")
        self.stdout.write(f"Timeout: {settings.OPENAI_TIMEOUT_SECONDS:g} seconds")
        self.stdout.write(f"Loaded .env: {settings.LOADED_ENV_PATH or 'none'}")
        reference = max(item.charged_at.date() for item in txns)
        selected_keys = set()
        for group in groups:
            key = group["normalized_merchant"]
            selected_keys.add(key)
            heuristic = analyze_merchant_group(group, reference)
            required = requires_llm_review(heuristic)
            fingerprint = transaction_fingerprint(user_id, key, group["_transaction_objects"])
            row = SubscriptionAssessment.objects.filter(
                user_id=user_id, normalized_merchant=key).first()
            validation = validate_cached_assessment(
                row, fingerprint, required, settings.OPENAI_SUBSCRIPTION_REVIEW_ENABLED,
                force=options["force"])
            would_call = bool(required and not validation.valid and
                              settings.OPENAI_SUBSCRIPTION_REVIEW_ENABLED and
                              settings.OPENAI_API_KEY and not options["no_call"])
            if options["no_call"]:
                reason = "no-call requested; diagnostics only"
            elif validation.valid:
                reason = "valid cached completed review" if required else "valid cached offline result"
            elif not required:
                reason = "heuristic result finalizes offline"
            elif not settings.OPENAI_SUBSCRIPTION_REVIEW_ENABLED:
                reason = "semantic review disabled"
            elif not settings.OPENAI_API_KEY:
                reason = "semantic review enabled but API key missing"
            else:
                reason = validation.reason.replace("_", " ")
            self.stdout.write("\nMerchant state")
            self.stdout.write(f'Merchant: {group["display_merchant"]}')
            self.stdout.write(f"Normalized merchant: {key}")
            self.stdout.write(f'Heuristic classification: {heuristic["classification"]}')
            self.stdout.write(f"Requires LLM review: {yes(required)}")
            self.stdout.write(f"Stored assessment exists: {yes(row is not None)}")
            self.stdout.write(f"Fingerprint matches: {yes(bool(row and row.input_fingerprint == fingerprint))}")
            self.stdout.write(f"Heuristic version matches: {yes(bool(row and row.heuristic_version == HEURISTIC_VERSION))}")
            self.stdout.write(f"Finalization version matches: {yes(bool(row and row.finalization_version == FINALIZATION_VERSION))}")
            self.stdout.write(f"Prompt version matches: {yes(bool(row and row.llm_prompt_version == LLM_PROMPT_VERSION))}")
            self.stdout.write(f"Model matches: {yes(bool(row and row.llm_model == settings.OPENAI_MODEL))}")
            self.stdout.write(f"Stored LLM status: {row.llm_review_status if row else 'none'}")
            self.stdout.write(f"Stored final classification: {row.final_classification if row else 'none'}")
            self.stdout.write(f"Stored assessment source: {row.assessment_source if row else 'none'}")
            self.stdout.write(f"Would call OpenAI now: {yes(would_call)}")
            self.stdout.write(f"Reason: {reason}")

        if not options["no_call"] and options["force"]:
            result = get_or_refresh_user_assessments(
                user_id, force=True, merchant_keys=selected_keys)
            self.stdout.write("\nForced refresh result")
            for row in result.assessments:
                self.stdout.write(f"{row.display_merchant}: {row.final_classification} "
                                  f"({row.llm_review_status}, {row.assessment_source})")
