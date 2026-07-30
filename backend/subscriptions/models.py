from django.db import models


class Transaction(models.Model):
    user_id = models.IntegerField(db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    merchant_name = models.CharField(max_length=255)
    charged_at = models.DateTimeField(db_index=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-charged_at"]

    def __str__(self):
        return f"{self.merchant_name} ${self.amount} @ {self.charged_at:%Y-%m-%d}"


class SubscriptionAssessment(models.Model):
    REVIEW_STATUSES = [(value, value.replace("_", " ").title()) for value in
                       ("not_required", "pending", "completed", "failed", "disabled",
                        "misconfigured")]
    FINAL_CLASSIFICATIONS = [(value, value.replace("_", " ").title()) for value in
                             ("subscription", "not_subscription", "uncertain")]
    SOURCES = [(value, value.replace("_", " ").title()) for value in
               ("heuristic", "llm_review", "heuristic_fallback")]

    user_id = models.IntegerField(db_index=True)
    normalized_merchant = models.CharField(max_length=255)
    display_merchant = models.CharField(max_length=255)
    input_fingerprint = models.CharField(max_length=64, db_index=True)
    heuristic_version = models.CharField(max_length=64)
    finalization_version = models.CharField(max_length=64)
    llm_prompt_version = models.CharField(max_length=64, blank=True)
    llm_model = models.CharField(max_length=100, blank=True)
    heuristic_classification = models.CharField(max_length=20)
    heuristic_payload = models.JSONField()
    llm_review_required = models.BooleanField(default=False)
    llm_review_status = models.CharField(max_length=20, choices=REVIEW_STATUSES,
                                         default="not_required")
    llm_payload = models.JSONField(null=True, blank=True)
    llm_error = models.TextField(blank=True)
    final_classification = models.CharField(max_length=24, choices=FINAL_CLASSIFICATIONS)
    final_confidence = models.FloatField()
    final_reason = models.TextField()
    cadence = models.CharField(max_length=64, blank=True)
    typical_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    next_predicted_charge_date = models.DateField(null=True, blank=True)
    assessment_source = models.CharField(max_length=24, choices=SOURCES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=("user_id", "normalized_merchant"), name="unique_user_merchant_assessment"
        )]
        ordering = ("normalized_merchant",)
