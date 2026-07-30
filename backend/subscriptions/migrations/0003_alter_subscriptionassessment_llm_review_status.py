from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0002_subscriptionassessment")]
    operations = [migrations.AlterField(
        model_name="subscriptionassessment",
        name="llm_review_status",
        field=models.CharField(
            choices=[("not_required", "Not Required"), ("pending", "Pending"),
                     ("completed", "Completed"), ("failed", "Failed"),
                     ("disabled", "Disabled"), ("misconfigured", "Misconfigured")],
            default="not_required", max_length=20),
    )]
