from unittest import TestCase

from .openai_review import _validate


class OpenAIOutputValidationTests(TestCase):
    def payload(self, **overrides):
        value = {
            "classification": "uncertain",
            "confidence": 0.5,
            "merchant_type": "unknown",
            "reason": "Evidence is insufficient.",
        }
        value.update(overrides)
        return value

    def test_valid_payload_is_normalized(self):
        result = _validate(self.payload(reason="  Evidence is insufficient.  "))
        self.assertEqual(result.reason, "Evidence is insufficient.")

    def test_rejects_non_finite_boolean_and_out_of_range_confidence(self):
        for confidence in (True, float("nan"), float("inf"), -0.01, 1.01, "0.5"):
            with self.subTest(confidence=confidence), self.assertRaises(ValueError):
                _validate(self.payload(confidence=confidence))

    def test_rejects_empty_reason_extra_fields_and_unsupported_values(self):
        invalid = [
            self.payload(reason=" "),
            {**self.payload(), "extra": "value"},
            self.payload(classification="likely"),
            self.payload(merchant_type="retail"),
        ]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                _validate(payload)
