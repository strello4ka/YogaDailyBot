import json
import unittest
from unittest.mock import Mock

from data.product_events import record_product_event


class ProductEventsTest(unittest.TestCase):
    def test_record_product_event_uses_idempotent_insert(self):
        cursor = Mock()

        record_product_event(
            cursor,
            10,
            "onboarding_button_clicked",
            "42:welcome:Покажи пример",
            metadata={"step": "welcome", "button": "Покажи пример"},
        )

        sql, params = cursor.execute.call_args.args
        self.assertIn("INSERT INTO product_events", sql)
        self.assertIn("ON CONFLICT", sql)
        self.assertEqual(params[:3], (10, "onboarding_button_clicked", "42:welcome:Покажи пример"))
        self.assertEqual(
            json.loads(params[4]),
            {"step": "welcome", "button": "Покажи пример"},
        )

    def test_record_product_event_rejects_invalid_name(self):
        with self.assertRaises(ValueError):
            record_product_event(Mock(), 10, "Invalid event", "1")


if __name__ == "__main__":
    unittest.main()
