from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="SubscriptionAssessment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_id", models.IntegerField(db_index=True)),
                ("normalized_merchant", models.CharField(max_length=255)),
                ("display_merchant", models.CharField(max_length=255)),
                ("input_fingerprint", models.CharField(db_index=True, max_length=64)),
                ("heuristic_version", models.CharField(max_length=64)),
                ("finalization_version", models.CharField(max_length=64)),
                ("llm_prompt_version", models.CharField(blank=True, max_length=64)),
                ("llm_model", models.CharField(blank=True, max_length=100)),
                ("heuristic_classification", models.CharField(max_length=20)),
                ("heuristic_payload", models.JSONField()),
                ("llm_review_required", models.BooleanField(default=False)),
                ("llm_review_status", models.CharField(choices=[("not_required", "Not Required"), ("pending", "Pending"), ("completed", "Completed"), ("failed", "Failed"), ("disabled", "Disabled")], default="not_required", max_length=20)),
                ("llm_payload", models.JSONField(blank=True, null=True)),
                ("llm_error", models.TextField(blank=True)),
                ("final_classification", models.CharField(choices=[("subscription", "Subscription"), ("not_subscription", "Not Subscription"), ("uncertain", "Uncertain")], max_length=24)),
                ("final_confidence", models.FloatField()),
                ("final_reason", models.TextField()),
                ("cadence", models.CharField(blank=True, max_length=64)),
                ("typical_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("next_predicted_charge_date", models.DateField(blank=True, null=True)),
                ("assessment_source", models.CharField(choices=[("heuristic", "Heuristic"), ("llm_review", "Llm Review"), ("heuristic_fallback", "Heuristic Fallback")], max_length=24)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("normalized_merchant",)},
        ),
        migrations.AddConstraint(model_name="subscriptionassessment", constraint=models.UniqueConstraint(fields=("user_id", "normalized_merchant"), name="unique_user_merchant_assessment")),
    ]
