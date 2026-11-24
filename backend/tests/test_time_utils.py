import unittest
from datetime import datetime, timedelta

from time_utils import COLOMBIA_TIMEZONE, now_colombia


class ColombiaTimeTests(unittest.TestCase):
    def test_now_colombia_returns_naive_utc_minus_five_wall_time(self):
        actual = now_colombia()
        expected = datetime.now(COLOMBIA_TIMEZONE).replace(tzinfo=None)

        self.assertIsNone(actual.tzinfo)
        self.assertLessEqual(abs(actual - expected), timedelta(seconds=1))


if __name__ == "__main__":
    unittest.main()
