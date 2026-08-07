"""Security boundaries for user-authored report templates.

Custom agent templates are displayed in a browser and rendered by WeasyPrint.
Both contexts must treat the template as untrusted: HTML/CSS is reduced to a
passive formatting allowlist before persistence, and PDF rendering uses a URL
fetcher that cannot reach the network or local filesystem.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional
from urllib.parse import urlsplit

import nh3
import tinycss2
from bs4 import BeautifulSoup


class TemplateSecurityError(ValueError):
    """A custom template cannot be made safe enough to persist."""


class ExternalTemplateResourceError(ValueError):
    """WeasyPrint attempted to load a non-embedded resource."""


MAX_TEMPLATE_HTML_CHARS = 2_000_000
MAX_TEMPLATE_CSS_CHARS = 1_000_000
MAX_EMBEDDED_DATA_URL_CHARS = 5_000_000

_PAGEBREAK_SENTINEL = "___ATTENLY_SAFE_PAGEBREAK_8F0DB5C4___"
_PAGEBREAK_RE = re.compile(r"<!--\s*pagebreak\s*-->", re.IGNORECASE)

_ALLOWED_HTML_TAGS = {
    "a",
    "address",
    "article",
    "aside",
    "b",
    "blockquote",
    "br",
    "caption",
    "code",
    "col",
    "colgroup",
    "dd",
    "div",
    "dl",
    "dt",
    "em",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "i",
    "img",
    "li",
    "main",
    "mark",
    "nav",
    "ol",
    "p",
    "pre",
    "s",
    "section",
    "small",
    "span",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}

# Inline style and every event attribute are intentionally absent. Image ``src``
# and related resource attributes are also absent, so a persisted custom
# template cannot make the browser or PDF renderer fetch an external resource.
_ALLOWED_HTML_ATTRIBUTES = {
    "*": {"class", "dir", "id", "lang", "title"},
    "img": {"alt", "height", "loading", "width"},
    "table": {"border", "cellpadding", "cellspacing", "width"},
    "th": {"colspan", "rowspan", "scope", "width"},
    "td": {"colspan", "rowspan", "height", "width"},
    "col": {"span", "width"},
    "colgroup": {"span"},
    "ol": {"reversed", "start", "type"},
    "li": {"value"},
}

# These elements can contain active or misleading content. Decomposing them
# before the allowlist pass prevents their text/CSS from surviving as inert but
# confusing output.
_DROP_WITH_CONTENT_TAGS = {
    "applet",
    "audio",
    "button",
    "canvas",
    "embed",
    "form",
    "head",
    "iframe",
    "input",
    "math",
    "noscript",
    "object",
    "option",
    "script",
    "select",
    "source",
    "style",
    "svg",
    "template",
    "textarea",
    "track",
    "video",
}

_ALLOWED_CSS_PROPERTIES = {
    "align-content",
    "align-items",
    "align-self",
    "background",
    "background-color",
    "border",
    "border-block",
    "border-block-color",
    "border-block-end",
    "border-block-start",
    "border-block-style",
    "border-block-width",
    "border-bottom",
    "border-bottom-color",
    "border-bottom-left-radius",
    "border-bottom-right-radius",
    "border-bottom-style",
    "border-bottom-width",
    "border-collapse",
    "border-color",
    "border-inline",
    "border-inline-color",
    "border-inline-end",
    "border-inline-start",
    "border-inline-style",
    "border-inline-width",
    "border-left",
    "border-left-color",
    "border-left-style",
    "border-left-width",
    "border-radius",
    "border-right",
    "border-right-color",
    "border-right-style",
    "border-right-width",
    "border-spacing",
    "border-style",
    "border-top",
    "border-top-color",
    "border-top-left-radius",
    "border-top-right-radius",
    "border-top-style",
    "border-top-width",
    "border-width",
    "box-decoration-break",
    "box-shadow",
    "box-sizing",
    "break-after",
    "break-before",
    "break-inside",
    "caption-side",
    "clear",
    "color",
    "column-count",
    "column-fill",
    "column-gap",
    "column-rule",
    "column-rule-color",
    "column-rule-style",
    "column-rule-width",
    "column-span",
    "column-width",
    "columns",
    "direction",
    "display",
    "empty-cells",
    "flex",
    "flex-basis",
    "flex-direction",
    "flex-flow",
    "flex-grow",
    "flex-shrink",
    "flex-wrap",
    "float",
    "font",
    "font-family",
    "font-feature-settings",
    "font-kerning",
    "font-size",
    "font-stretch",
    "font-style",
    "font-variant",
    "font-variant-caps",
    "font-variant-ligatures",
    "font-weight",
    "gap",
    "grid",
    "grid-area",
    "grid-auto-columns",
    "grid-auto-flow",
    "grid-auto-rows",
    "grid-column",
    "grid-column-end",
    "grid-column-gap",
    "grid-column-start",
    "grid-gap",
    "grid-row",
    "grid-row-end",
    "grid-row-gap",
    "grid-row-start",
    "grid-template",
    "grid-template-areas",
    "grid-template-columns",
    "grid-template-rows",
    "height",
    "hyphens",
    "justify-content",
    "justify-items",
    "justify-self",
    "letter-spacing",
    "line-break",
    "line-height",
    "list-style",
    "list-style-position",
    "list-style-type",
    "margin",
    "margin-block",
    "margin-block-end",
    "margin-block-start",
    "margin-bottom",
    "margin-inline",
    "margin-inline-end",
    "margin-inline-start",
    "margin-left",
    "margin-right",
    "margin-top",
    "max-height",
    "max-width",
    "min-height",
    "min-width",
    "object-fit",
    "object-position",
    "orphans",
    "overflow",
    "overflow-wrap",
    "overflow-x",
    "overflow-y",
    "padding",
    "padding-block",
    "padding-block-end",
    "padding-block-start",
    "padding-bottom",
    "padding-inline",
    "padding-inline-end",
    "padding-inline-start",
    "padding-left",
    "padding-right",
    "padding-top",
    "page-break-after",
    "page-break-before",
    "page-break-inside",
    "row-gap",
    "size",
    "table-layout",
    "text-align",
    "text-align-last",
    "text-decoration",
    "text-decoration-color",
    "text-decoration-line",
    "text-decoration-style",
    "text-indent",
    "text-justify",
    "text-overflow",
    "text-shadow",
    "text-transform",
    "vertical-align",
    "white-space",
    "widows",
    "width",
    "word-break",
    "word-spacing",
    "word-wrap",
}
_BLOCKED_CSS_FUNCTIONS = {
    "-moz-element",
    "-webkit-canvas",
    "-webkit-cross-fade",
    "-webkit-image-set",
    "cross-fade",
    "element",
    "expression",
    "image",
    "image-set",
    "paint",
    "src",
    "url",
}
_GROUP_CSS_AT_RULES = {"media", "supports"}
_DECLARATION_CSS_AT_RULES = {"page"}


def sanitize_custom_template_html(html: str) -> str:
    """Return passive, resource-free HTML suitable for persistence."""

    if not isinstance(html, str):
        raise TemplateSecurityError("Report template HTML must be text")
    if len(html) > MAX_TEMPLATE_HTML_CHARS:
        raise TemplateSecurityError("Report template HTML is too large")
    if not html.strip():
        raise TemplateSecurityError("Report template HTML cannot be empty")

    try:
        preserved = _PAGEBREAK_RE.sub(_PAGEBREAK_SENTINEL, html)
        soup = BeautifulSoup(preserved, "html.parser")
        for tag in soup.find_all(_DROP_WITH_CONTENT_TAGS):
            tag.decompose()

        sanitized = nh3.clean(
            str(soup),
            tags=set(_ALLOWED_HTML_TAGS),
            attributes={tag: set(values) for tag, values in _ALLOWED_HTML_ATTRIBUTES.items()},
            link_rel="noopener noreferrer",
            url_schemes={"http", "https", "mailto"},
        )
        sanitized = sanitized.replace(_PAGEBREAK_SENTINEL, "<!-- pagebreak -->").strip()
    except TemplateSecurityError:
        raise
    except Exception as exc:
        raise TemplateSecurityError("Report template HTML could not be sanitized") from exc

    if not sanitized:
        raise TemplateSecurityError("Report template HTML contains no safe content")
    return sanitized


def _normalize_css_escapes(value: str) -> str:
    def replace_escape(match: re.Match[str]) -> str:
        try:
            codepoint = int(match.group(1), 16)
            return chr(codepoint) if codepoint <= 0x10FFFF else ""
        except (ValueError, OverflowError):
            return ""

    return re.sub(r"\\([0-9a-fA-F]{1,6})(?:\r\n|[\t\n\f\r ])?", replace_escape, value)


def _tokens_contain_blocked_resource(tokens: Iterable[Any]) -> bool:
    for token in tokens:
        token_type = getattr(token, "type", "")
        if token_type == "url":
            return True
        if token_type == "function":
            function_name = (
                getattr(token, "lower_name", None)
                or getattr(token, "name", "")
            ).lower()
            if function_name in _BLOCKED_CSS_FUNCTIONS:
                return True
            if _tokens_contain_blocked_resource(getattr(token, "arguments", ())):
                return True

        nested_content = getattr(token, "content", None)
        if nested_content and _tokens_contain_blocked_resource(nested_content):
            return True

    return False


def _css_value_is_safe(tokens: Iterable[Any]) -> bool:
    token_list = list(tokens)
    if _tokens_contain_blocked_resource(token_list):
        return False

    serialized = tinycss2.serialize(token_list)
    normalized = _normalize_css_escapes(serialized)
    normalized = re.sub(r"/\*.*?\*/", "", normalized, flags=re.DOTALL)
    if any(character in normalized for character in ("<", ">", "\x00")):
        # CSS is embedded inside an HTML <style> element during PDF rendering.
        # Reject markup delimiters so CSS cannot terminate that element.
        return False
    compact = re.sub(r"\s+", "", normalized).casefold()
    return not any(
        blocked in compact
        for blocked in (
            "javascript:",
            "vbscript:",
            "expression(",
            "-moz-binding",
            "behavior:",
            "@import",
        )
    )


def _css_selector_is_safe(selector: str) -> bool:
    normalized = _normalize_css_escapes(selector)
    normalized = re.sub(r"/\*.*?\*/", "", normalized, flags=re.DOTALL).casefold()
    if any(character in normalized for character in ("<", ">", "\x00")):
        return False

    # The browser wraps report HTML in this class. Letting authored CSS name the
    # boundary would allow it to bypass selector scoping and style the host UI.
    if ".template-isolated-content" in normalized:
        return False

    # The frontend historically maps a leading body selector to the report
    # boundary itself. Reject document-root selectors instead of relying on that
    # behavior, including escaped spellings normalized above.
    return re.search(r"(?<![-_a-z0-9])(?:html|body|:root)(?![-_a-z0-9])", normalized) is None


def _sanitize_declaration_block(content: Iterable[Any]) -> str:
    declarations = tinycss2.parse_declaration_list(
        content,
        skip_comments=True,
        skip_whitespace=True,
    )
    safe_declarations: list[str] = []
    for declaration in declarations:
        if declaration.type != "declaration":
            continue
        property_name = (
            getattr(declaration, "lower_name", None)
            or declaration.name
        ).casefold()
        if property_name not in _ALLOWED_CSS_PROPERTIES:
            continue
        if not _css_value_is_safe(declaration.value):
            continue

        value = tinycss2.serialize(declaration.value).strip()
        if not value:
            continue
        important = " !important" if declaration.important else ""
        safe_declarations.append(f"{declaration.name}: {value}{important};")
    return " ".join(safe_declarations)


def _sanitize_css_rules(rules: Iterable[Any]) -> list[str]:
    safe_rules: list[str] = []
    for rule in rules:
        if rule.type == "qualified-rule":
            if _tokens_contain_blocked_resource(rule.prelude):
                continue
            selector = tinycss2.serialize(rule.prelude).strip()
            if not _css_selector_is_safe(selector):
                continue
            declarations = _sanitize_declaration_block(rule.content)
            if selector and declarations:
                safe_rules.append(f"{selector} {{ {declarations} }}")
            continue

        if rule.type != "at-rule":
            continue
        at_keyword = rule.at_keyword.casefold()
        if rule.content is None:
            # This drops @import, @charset, @namespace, and all other statement
            # at-rules, including obfuscated variants parsed by tinycss2.
            continue
        if _tokens_contain_blocked_resource(rule.prelude):
            continue

        prelude = tinycss2.serialize(rule.prelude).strip()
        if any(character in prelude for character in ("<", ">", "\x00")):
            continue
        if at_keyword in _GROUP_CSS_AT_RULES:
            nested = tinycss2.parse_rule_list(
                rule.content,
                skip_comments=True,
                skip_whitespace=True,
            )
            nested_rules = _sanitize_css_rules(nested)
            if nested_rules:
                suffix = f" {prelude}" if prelude else ""
                safe_rules.append(
                    f"@{at_keyword}{suffix} {{ {' '.join(nested_rules)} }}"
                )
        elif at_keyword in _DECLARATION_CSS_AT_RULES:
            declarations = _sanitize_declaration_block(rule.content)
            if declarations:
                suffix = f" {prelude}" if prelude else ""
                safe_rules.append(f"@{at_keyword}{suffix} {{ {declarations} }}")
        # @import, @font-face, @namespace, @charset, animation definitions,
        # and unknown at-rules are deliberately dropped.

    return safe_rules


def sanitize_custom_template_css(css: Optional[str]) -> Optional[str]:
    """Return CSS with all resource loading and active constructs removed."""

    if css is None:
        return None
    if not isinstance(css, str):
        raise TemplateSecurityError("Report template CSS must be text")
    if len(css) > MAX_TEMPLATE_CSS_CHARS:
        raise TemplateSecurityError("Report template CSS is too large")
    if not css.strip():
        return ""

    try:
        rules = tinycss2.parse_stylesheet(
            css,
            skip_comments=True,
            skip_whitespace=True,
        )
        return "\n".join(_sanitize_css_rules(rules))
    except Exception as exc:
        raise TemplateSecurityError("Report template CSS could not be sanitized") from exc


def sanitize_custom_agent_template(
    html: str,
    css: Optional[str],
) -> tuple[str, Optional[str]]:
    """Sanitize both persisted custom-template fields in one operation."""

    return sanitize_custom_template_html(html), sanitize_custom_template_css(css)


def restricted_weasyprint_url_fetcher(
    url: str,
    timeout: int = 10,
    ssl_context: Any = None,
) -> dict[str, Any]:
    """Allow embedded ``data:`` URLs only; reject network and filesystem I/O."""

    if not isinstance(url, str):
        raise ExternalTemplateResourceError("Template resources must use embedded data URLs")
    scheme = urlsplit(url).scheme.casefold()
    if scheme != "data":
        raise ExternalTemplateResourceError(
            "External and local template resources are disabled"
        )
    if len(url) > MAX_EMBEDDED_DATA_URL_CHARS:
        raise ExternalTemplateResourceError("Embedded template resource is too large")
    header, separator, _ = url.partition(",")
    if (
        not separator
        or not re.fullmatch(
            r"data:image/(?:png|jpeg|gif|webp);base64",
            header,
            flags=re.IGNORECASE,
        )
    ):
        raise ExternalTemplateResourceError(
            "Only base64-encoded raster image resources are allowed"
        )

    # Import lazily so persistence-only workers do not initialize WeasyPrint's
    # native rendering stack merely to sanitize HTML/CSS.
    from weasyprint import default_url_fetcher

    return default_url_fetcher(url, timeout=timeout, ssl_context=ssl_context)
