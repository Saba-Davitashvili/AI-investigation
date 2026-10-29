import unittest

from investigator import (
    InvestigationError,
    InvestigationResult,
    validate_result
)


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.sources = {
            "S1": {
                "text": "Arthur's Magazine began in 1844."
            }
        }

    def make_result(
        self,
        source_id="S1",
        quote="began in 1844"
    ):
        return InvestigationResult(
            status="answered",
            findings=[
                {
                    "statement": (
                        "Arthur's Magazine began in 1844."
                    ),
                    "evidence": [
                        {
                            "source_id": source_id,
                            "quote": quote
                        }
                    ]
                }
            ],
            limitations=[]
        )

    def test_accepts_existing_source_and_exact_quote(self):
        validate_result(self.make_result(), self.sources)

    def test_rejects_unknown_source(self):
        result = self.make_result(source_id="S999")

        with self.assertRaises(InvestigationError):
            validate_result(result, self.sources)

    def test_rejects_invented_quote(self):
        result = self.make_result(quote="began in 1900")

        with self.assertRaises(InvestigationError):
            validate_result(result, self.sources)

    def test_rejects_whitespace_quote(self):
        result = self.make_result(quote="   ")

        with self.assertRaises(InvestigationError):
            validate_result(result, self.sources)

    def test_rejects_answer_without_findings(self):
        result = InvestigationResult(
            status="answered",
            findings=[],
            limitations=[]
        )

        with self.assertRaises(InvestigationError):
            validate_result(result, self.sources)

    def test_accepts_explained_abstention(self):
        result = InvestigationResult(
            status="insufficient",
            findings=[],
            limitations=[
                "The retrieved passages do not provide this fact."
            ]
        )

        validate_result(result, self.sources)

    def test_rejects_unexplained_abstention(self):
        result = InvestigationResult(
            status="insufficient",
            findings=[],
            limitations=[]
        )

        with self.assertRaises(InvestigationError):
            validate_result(result, self.sources)


if __name__ == "__main__":
    unittest.main()