"""Focused tests for custom-template sanitization and PDF resource isolation."""

import unittest
import importlib.util
import sys
from types import SimpleNamespace
from types import ModuleType
from unittest import mock

from app.services.template_security import (
    ExternalTemplateResourceError,
    TemplateSecurityError,
    restricted_weasyprint_url_fetcher,
    sanitize_custom_agent_template,
    sanitize_custom_template_css,
    sanitize_custom_template_html,
)


class CustomTemplateSanitizerTests(unittest.TestCase):
    def test_html_strips_active_content_inline_style_and_resource_urls(self) -> None:
        unsafe = """
        <html><head>
          <style>.stolen { background: url(https://tracker.example/pixel); }</style>
          <script>window.stolen = true</script>
        </head><body>
          <div class="report" style="background:url(file:///etc/passwd)" onclick="steal()">
            <iframe src="https://tracker.example/frame"></iframe>
            <img src="https://tracker.example/pixel" srcset="https://tracker.example/2x 2x"
                 onerror="steal()" alt="Logo" width="50">
            <a href="javascript:steal()" target="_blank">Unsafe link</a>
            <a href="https://example.com/reference" target="_blank">Reference text</a>
            <p>{{answer}}</p>
            <!-- PAGEBREAK -->
          </div>
        </body></html>
        """

        sanitized = sanitize_custom_template_html(unsafe)
        lowered = sanitized.casefold()

        self.assertIn('class="report"', sanitized)
        self.assertIn("{{answer}}", sanitized)
        self.assertIn("<!-- pagebreak -->", sanitized)
        self.assertIn("Reference text", sanitized)
        self.assertNotIn("href=", lowered)
        self.assertNotIn("target=", lowered)
        self.assertNotIn("window.stolen", sanitized)
        self.assertNotIn("<script", lowered)
        self.assertNotIn("<style", lowered)
        self.assertNotIn("<iframe", lowered)
        self.assertNotIn("onclick", lowered)
        self.assertNotIn("onerror", lowered)
        self.assertNotIn("style=", lowered)
        self.assertNotIn("src=", lowered)
        self.assertNotIn("srcset", lowered)
        self.assertNotIn("javascript:", lowered)
        self.assertNotIn("tracker.example", lowered)

    def test_html_rejects_template_with_only_active_content(self) -> None:
        with self.assertRaises(TemplateSecurityError):
            sanitize_custom_template_html(
                "<script>steal()</script><iframe src='https://example.com'></iframe>"
            )

    def test_css_strips_urls_imports_resource_rules_and_active_constructs(self) -> None:
        unsafe = r"""
        @import url("https://tracker.example/import.css");
        @font-face { font-family: Stolen; src: url(file:///etc/passwd); }
        .report {
          color: #123456;
          margin: 1rem;
          background-image: url(https://tracker.example/pixel);
          background: src("https://attacker.example/pixel");
          list-style: src(file:///etc/passwd);
          width: expression(alert(1));
          behavior: url(malware.htc);
        }
        @media print {
          .report {
            color: black;
            list-style-image: u\72l("https://tracker.example/list");
          }
        }
        @page {
          size: letter;
          margin: 0.75in;
          background: url(file:///etc/passwd);
        }
        """

        sanitized = sanitize_custom_template_css(unsafe) or ""
        lowered = sanitized.casefold()

        self.assertIn("color: #123456", sanitized)
        self.assertIn("margin: 1rem", sanitized)
        self.assertIn("@media print", sanitized)
        self.assertIn("color: black", sanitized)
        self.assertIn("@page", sanitized)
        self.assertIn("size: letter", sanitized)
        self.assertNotIn("url", lowered)
        self.assertNotIn("src(", lowered)
        self.assertNotIn("@import", lowered)
        self.assertNotIn("@font-face", lowered)
        self.assertNotIn("expression", lowered)
        self.assertNotIn("behavior", lowered)
        self.assertNotIn("tracker.example", lowered)
        self.assertNotIn("attacker.example", lowered)
        self.assertNotIn("file:", lowered)

    def test_css_cannot_break_out_of_the_generated_style_element(self) -> None:
        sanitized = sanitize_custom_template_css(
            'p { color: red; content: "</style><script>steal()</script>"; } '
            '</style><img src=x onerror=steal()> { color: blue; }'
        ) or ""

        self.assertNotIn("<", sanitized)
        self.assertNotIn(">", sanitized)
        self.assertIn("color: red", sanitized)

    def test_css_cannot_target_host_boundary_or_create_viewport_overlay(self) -> None:
        sanitized = sanitize_custom_template_css(
            """
            .template-isolated-content, body, :root {
              position: fixed;
              inset: 0;
              z-index: 2147483647;
              pointer-events: auto;
              background: white;
            }
            .report-card {
              color: #123456;
              position: fixed;
              top: 0;
              transform: translateX(-100vw);
              z-index: 9999;
              padding: 1rem;
            }
            """
        ) or ""

        lowered = sanitized.casefold()
        self.assertNotIn("template-isolated-content", lowered)
        self.assertNotIn("position", lowered)
        self.assertNotIn("inset", lowered)
        self.assertNotIn("z-index", lowered)
        self.assertNotIn("pointer-events", lowered)
        self.assertNotIn("transform", lowered)
        self.assertIn(".report-card", sanitized)
        self.assertIn("color: #123456", sanitized)
        self.assertIn("padding: 1rem", sanitized)

    def test_combined_sanitizer_preserves_optional_css(self) -> None:
        html, css = sanitize_custom_agent_template(
            "<p style='color:red'>Safe {{answer}}</p>",
            None,
        )
        self.assertEqual("<p>Safe {{answer}}</p>", html)
        self.assertIsNone(css)


class RestrictedWeasyPrintFetcherTests(unittest.TestCase):
    def test_rejects_network_filesystem_relative_and_unknown_resources(self) -> None:
        for url in (
            "http://169.254.169.254/latest/meta-data",
            "https://tracker.example/pixel",
            "file:///etc/passwd",
            "//tracker.example/protocol-relative",
            "relative/image.png",
            "C:\\Windows\\win.ini",
            "ftp://tracker.example/file",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ExternalTemplateResourceError):
                    restricted_weasyprint_url_fetcher(url)

    def test_allows_bounded_embedded_data_resources(self) -> None:
        expected = {"string": b"image", "mime_type": "image/png"}
        fake_weasyprint = ModuleType("weasyprint")
        default_fetcher = mock.Mock(return_value=expected)
        fake_weasyprint.default_url_fetcher = default_fetcher
        with mock.patch.dict(sys.modules, {"weasyprint": fake_weasyprint}):
            result = restricted_weasyprint_url_fetcher(
                "data:image/png;base64,aW1hZ2U=",
                timeout=3,
            )

        self.assertEqual(expected, result)
        default_fetcher.assert_called_once_with(
            "data:image/png;base64,aW1hZ2U=",
            timeout=3,
            ssl_context=None,
        )

    def test_rejects_active_or_non_image_data_resources(self) -> None:
        for url in (
            "data:text/html;base64,PHNjcmlwdD5zdGVhbCgpPC9zY3JpcHQ+",
            "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=",
            "data:image/png,not-base64",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ExternalTemplateResourceError):
                    restricted_weasyprint_url_fetcher(url)

    def test_pdf_generator_passes_restricted_fetcher_to_weasyprint(self) -> None:
        if importlib.util.find_spec("weasyprint") is None:
            self.skipTest("WeasyPrint test dependency is unavailable")
        try:
            from app.services.pdf_generator import WeasyPrintPDFGenerator
        except ImportError as exc:
            self.skipTest(f"WeasyPrint test dependency is unavailable: {exc}")

        generator = WeasyPrintPDFGenerator()
        agent = SimpleNamespace(
            name="Safe agent",
            reportTemplate="<p>Hello</p>",
            reportTemplateCss="p { color: black; }",
            questions=[],
        )
        html_document = mock.Mock()
        html_document.write_pdf.return_value = b"pdf"

        with mock.patch(
            "app.services.pdf_generator.HTML",
            return_value=html_document,
        ) as html_class:
            result = generator.generate_pdf_report(agent, {"answers": {}})

        self.assertEqual(b"pdf", result)
        self.assertIs(
            restricted_weasyprint_url_fetcher,
            html_class.call_args.kwargs["url_fetcher"],
        )

    def test_template_ingest_pdf_conversion_passes_restricted_fetcher(self) -> None:
        if importlib.util.find_spec("weasyprint") is None:
            self.skipTest("WeasyPrint test dependency is unavailable")
        try:
            from app.services.template_ingest_service import TemplateIngestService
        except ImportError as exc:
            self.skipTest(f"WeasyPrint test dependency is unavailable: {exc}")

        service = TemplateIngestService()
        html_document = mock.Mock()
        html_document.write_pdf.return_value = b"pdf"

        with mock.patch("weasyprint.HTML", return_value=html_document) as html_class:
            result = service._html_to_pdf("<p>Template</p>")

        self.assertEqual(b"pdf", result)
        self.assertIs(
            restricted_weasyprint_url_fetcher,
            html_class.call_args.kwargs["url_fetcher"],
        )


if __name__ == "__main__":
    unittest.main()
