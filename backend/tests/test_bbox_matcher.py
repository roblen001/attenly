import unittest

from app.services.bbox_matcher import BBoxMatcher


class BBoxMatcherTests(unittest.TestCase):
    def test_matches_initials_and_trailing_punctuation(self):
        document_bboxes = {
            "pages": [
                {
                    "page_number": 1,
                    "lines": [
                        {
                            "line_text": "Dr. P.N. Cundall,",
                            "words": [
                                {"text": "Dr.", "bbox": [0.164, 0.298, 0.197, 0.314], "confidence": 0.999},
                                {"text": "P.N.", "bbox": [0.203, 0.298, 0.244, 0.313], "confidence": 0.999},
                                {"text": "Cundall,", "bbox": [0.253, 0.298, 0.331, 0.313], "confidence": 0.996},
                            ],
                        }
                    ],
                }
            ]
        }

        result = BBoxMatcher().match_quote_to_words(
            "Dr. P.N. Cundall,",
            document_bboxes,
            page_number=1,
        )

        self.assertEqual(["Dr.", "P.N.", "Cundall,"], [span["text"] for span in result])


if __name__ == "__main__":
    unittest.main()
