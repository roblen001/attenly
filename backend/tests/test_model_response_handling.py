import unittest
from unittest.mock import patch

from app.schemas import AnswerType, ColumnDefinition, QuestionOut
from app.services.llm_service import LLMService
from app.services.template_ingest_service import TemplateIngestService


class LLMStructuredOutputTests(unittest.TestCase):
    def setUp(self):
        self.service = object.__new__(LLMService)

    def test_string_question_schema_requires_placeholder(self):
        question = QuestionOut(
            id="test",
            placeholder="{{Test Question}}",
            prompt="What happened?",
        )

        schema = self.service._get_response_json_schema(question)

        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["required"], ["{{Test Question}}"])
        self.assertEqual(
            schema["properties"]["{{Test Question}}"],
            {"type": "string"},
        )

    def test_table_question_schema_preserves_column_contract(self):
        question = QuestionOut(
            id="test",
            placeholder="{{People}}",
            prompt="List the people.",
            answer_type=AnswerType.TABLE,
            columns=[
                ColumnDefinition(key="name", header="Name"),
                ColumnDefinition(key="role", header="Role"),
            ],
        )

        schema = self.service._get_response_json_schema(question)
        row_schema = schema["properties"]["{{People}}"]["items"]

        self.assertEqual(row_schema["required"], ["name", "role"])
        self.assertEqual(
            row_schema["properties"],
            {"name": {"type": "string"}, "role": {"type": "string"}},
        )

    def test_invalid_model_json_is_returned_as_an_error(self):
        question = QuestionOut(
            id="test",
            placeholder="{{Test Question}}",
            prompt="What happened?",
        )
        token_usage = {"input_tokens": 12, "output_tokens": 7}
        self.service._generate_json_text_sync = lambda *args, **kwargs: (
            '{"{{Test Question}}": "unterminated}',
            token_usage,
        )

        placeholder, result = self.service._process_single_question_sync(
            {"question": question, "relevant_chunks": []},
            {},
        )

        self.assertEqual(placeholder, "{{Test Question}}")
        self.assertIn("error", result)
        self.assertEqual(result["token_usage"], token_usage)


class TemplateIngestFailureTests(unittest.TestCase):
    def setUp(self):
        self.service = object.__new__(TemplateIngestService)
        self.service.provider = "gemini"
        self.service.model_name = "gemini-test-model"

    def test_failed_pdf_ingest_does_not_return_blank_success(self):
        self.service._normalize_with_gemini = lambda *args, **kwargs: ("", "")

        result = self.service.process_template_file(b"%PDF", "template.pdf")

        self.assertFalse(result.success)
        self.assertEqual(result.source, "error")
        self.assertEqual(result.html_body, "")
        self.assertEqual(result.css, "")

    def test_template_schema_requires_html_and_css(self):
        schema = self.service.RESPONSE_SCHEMA

        self.assertEqual(schema["required"], ["html_body", "css"])
        self.assertEqual(schema["properties"]["html_body"], {"type": "string"})
        self.assertEqual(schema["properties"]["css"], {"type": "string"})

    def test_gemini_api_key_is_redacted_from_errors(self):
        exposed_key = "test-secret-key"
        error = RuntimeError(
            "API key not valid; API_KEY_INVALID at "
            f"https://example.test?key={exposed_key}"
        )

        with patch(
            "app.services.template_ingest_service.GEMINI_API_KEY",
            exposed_key,
        ):
            message = self.service._safe_gemini_error_message(error)

        self.assertNotIn(exposed_key, message)
        self.assertIn("rejected the API key", message)


if __name__ == "__main__":
    unittest.main()
