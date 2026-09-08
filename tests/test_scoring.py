import unittest

from checker import calculate_ngram_overlap
from utils import normalize_text


class NgramOverlapTests(unittest.TestCase):
    def test_identical_text_scores_full_coverage_with_occurrences(self):
        text = "the cat sat on the mat and the dog ran with the cat"
        coverage, count, _ = calculate_ngram_overlap(text, text)
        self.assertEqual(coverage, 1.0)
        self.assertEqual(count, len(text.split()))

    def test_repeated_vocabulary_is_not_undercounted(self):
        # Old set-based counting scored this ~0.69; positional counting is exact.
        text = " ".join(["quantum"] * 20 + ["field"] * 20)
        coverage, count, _ = calculate_ngram_overlap(text, text)
        self.assertEqual(coverage, 1.0)
        self.assertEqual(count, 40)

    def test_single_shared_trigram(self):
        student = "alpha beta gamma " + " ".join(f"u{i}" for i in range(37))
        db = "alpha beta gamma " + " ".join(f"v{i}" for i in range(37))
        coverage, count, matched = calculate_ngram_overlap(student, db)
        self.assertEqual(count, 3)
        self.assertAlmostEqual(coverage, 3 / 40)
        self.assertEqual(matched, {"alpha", "beta", "gamma"})

    def test_disjoint_texts_score_zero(self):
        coverage, count, matched = calculate_ngram_overlap(
            "apples oranges bananas grapes", "quantum field theory gravity"
        )
        self.assertEqual((coverage, count, matched), (0.0, 0, set()))

    def test_short_texts_score_zero(self):
        self.assertEqual(
            calculate_ngram_overlap("hi", "hello world foo bar"), (0.0, 0, set())
        )


class NormalizeTextTests(unittest.TestCase):
    def test_normal_prose_with_symbols_survives(self):
        for text in [
            "The result is E=mc2 for energy",
            "Use client/server and/or C++ code",
            "Contact a+b and see 10/20 ratio",
        ]:
            self.assertIn("E=mc2" if "E=mc2" in text else text.split()[0], normalize_text(text))
            self.assertTrue(len(normalize_text(text)) > 10)

    def test_symbol_dense_garble_is_removed(self):
        text = "Normal opening words here\n" + "= = = ^ ^ _ _ { } ∑ ∫ α β " * 3
        cleaned = normalize_text(text)
        self.assertIn("Normal opening words here", cleaned)
        self.assertNotIn("∑", cleaned)

    def test_citations_still_removed(self):
        self.assertNotIn("[1]", normalize_text("As shown before [1] the effect holds"))


if __name__ == "__main__":
    unittest.main()
