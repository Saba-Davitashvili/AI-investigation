import unittest

from evaluate_extended import check_case
from setup_demo_access import update_assignments


class ExtendedAssertionTests(unittest.TestCase):
    def test_formatted_number_and_real_quote_pass(self):
        case = {"expected_status": "answered", "expected_fact_groups": [["12000"]], "expected_cited_files": ["reference.md"]}
        result = {"status": "answered", "findings": [{"statement": "Budget: 12,000 GEL.", "evidence": [{"source_id": "S1", "quote": "Budget: 12000 GEL."}]}], "sources": {"S1": {"title": "reference.md", "text": "Budget: 12000 GEL."}}, "limitations": []}
        self.assertTrue(check_case(case, result)["passed_all_assertions"])

    def test_invented_reference_fails_even_with_matching_facts(self):
        case = {"expected_status": "answered", "expected_fact_groups": [["12000"]], "expected_cited_files": []}
        result = {"status": "answered", "findings": [{"statement": "Budget 12000", "evidence": [{"source_id": "S999", "quote": "Budget 12000"}]}], "sources": {}, "limitations": []}
        self.assertFalse(check_case(case, result)["passed_all_assertions"])

    def test_access_setup_preserves_provider_key_and_removes_duplicate_assignment(self):
        text = "# local config\nGROQ_API_KEY=synthetic-placeholder\nDEMO_PASSWORD=old\nDEMO_PASSWORD=other\n"
        result = update_assignments(text, {"DEMO_PASSWORD": "new-test-value"})
        self.assertIn("GROQ_API_KEY=synthetic-placeholder", result)
        self.assertEqual(result.count("DEMO_PASSWORD="), 1)
        self.assertIn("DEMO_PASSWORD=new-test-value", result)


if __name__ == "__main__":
    unittest.main()
