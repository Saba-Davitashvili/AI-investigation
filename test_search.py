import unittest

from search import search_documents, tokenize


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.documents = [
            {
                "id": "doc-001",
                "title": "Python",
                "text": "Python was created by Guido van Rossum."
            },
            {
                "id": "doc-002",
                "title": "Guido van Rossum",
                "text": "Guido van Rossum was born in the Netherlands."
            },
            {
                "id": "doc-003",
                "title": "Java",
                "text": "Java was developed at Sun Microsystems."
            }
        ]

    def test_tokenize_ignores_case_and_punctuation(self):
        actual = tokenize("PYTHON, Netherlands!")
        self.assertEqual(actual, {"python", "netherlands"})

    def test_more_matching_words_rank_first(self):
        results = search_documents("Guido Netherlands", self.documents)

        actual_ids = [result["document"]["id"] for result in results]

        self.assertGreater(
            results[0]["score"],
            results[1]["score"]
        )
    def test_unknown_word_returns_no_results(self):
        results = search_documents("unicorn", self.documents)
        self.assertEqual(results, [])

    def test_empty_query_returns_no_results(self):
        results = search_documents("", self.documents)
        self.assertEqual(results, [])

    def test_repeated_words_do_not_increase_score(self):
        results = search_documents("Java Java Java", self.documents)

        self.assertEqual(len(results), 1)
        single_word_results = search_documents(
            "Java", self.documents
        )

        self.assertAlmostEqual(
            results[0]["score"],
            single_word_results[0]["score"]
        )


if __name__ == "__main__":
    unittest.main()