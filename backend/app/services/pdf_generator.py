"""
WeasyPrint PDF Generator Service

Professional PDF generation service that converts HTML templates to 
pixel-perfect PDFs using WeasyPrint, preserving all CSS styling, colors, 
layouts, and visual elements exactly as they appear in the browser.
"""

import logging
from io import BytesIO
from typing import Dict, Any
from weasyprint import HTML, CSS
from app.schemas import Agent

logger = logging.getLogger(__name__)


class WeasyPrintPDFGenerator:
    """Professional PDF generator using WeasyPrint for pixel-perfect HTML-to-PDF conversion"""

    def __init__(self):
        self.quote_counter = 1

    def generate_pdf_report(self, agent: Agent, report_data: Dict[str, Any],
                          with_references: bool = False) -> bytes:
        """
        Generate pixel-perfect PDF report from HTML template

        Args:
            agent: Agent configuration with HTML template
            report_data: Report data with answers and quotes
            with_references: Whether to include reference section

        Returns:
            PDF content as bytes
        """
        try:
            # Reset quote counter for this document
            self.quote_counter = 1
            
            # Populate HTML template with answers and references
            populated_html = self._populate_html_template(
                agent.reportTemplate, 
                report_data, 
                with_references
            )
            
            # Add reference section if requested
            if with_references:
                populated_html = self._add_reference_section(populated_html, report_data)
            
            # Generate PDF using WeasyPrint - preserves ALL styling
            pdf_bytes = HTML(string=populated_html).write_pdf()
            
            logger.info(f"Successfully generated pixel-perfect PDF report for agent: {agent.name}")
            return pdf_bytes

        except Exception as e:
            logger.error(f"Failed to generate PDF report: {e}")
            raise ValueError(f"PDF generation failed: {str(e)}")

    def _populate_html_template(self, template_html: str, report_data: Dict[str, Any],
                              with_references: bool) -> str:
        """Populate HTML template with answers and proper reference formatting"""
        populated_html = template_html
        answers = report_data.get('answers', {})
        
        # Reset quote counter
        self.quote_counter = 1
        
        # Replace placeholders with answers and references
        for placeholder, answer_data in answers.items():
            placeholder_pattern = f"{{{{{placeholder}}}}}"
            
            if placeholder_pattern in populated_html:
                answer_text = answer_data.get("answer", "")
                quotes = answer_data.get("quotes", [])
                
                # Add reference formatting
                if quotes and answer_text:
                    if with_references:
                        # Use square brackets for references [1] [2] [3]
                        references = []
                        for i in range(len(quotes)):
                            references.append(f'[{self.quote_counter + i}]')
                        reference_text = ''.join(references)
                        answer_with_refs = f"{answer_text}{reference_text}"
                    else:
                        # Use superscript numbers ¹ ² ³
                        superscripts = []
                        for i in range(len(quotes)):
                            superscripts.append(f'<sup>{self.quote_counter + i}</sup>')
                        reference_text = ''.join(superscripts)
                        answer_with_refs = f"{answer_text}{reference_text}"
                else:
                    answer_with_refs = answer_text
                
                populated_html = populated_html.replace(placeholder_pattern, answer_with_refs)
                self.quote_counter += len(quotes)
        
        return populated_html

    def _add_reference_section(self, html_content: str, report_data: Dict[str, Any]) -> str:
        """Add professional reference section to HTML before PDF generation"""
        
        # Collect all quotes from answers
        reference_counter = 1
        references_html = []
        answers = report_data.get('answers', {})
        
        for answer_data in answers.values():
            quotes = answer_data.get('quotes', [])
            for quote in quotes:
                # Format reference entry
                document_name = quote.get('document_filename', 'Unknown Document')
                page_info = quote.get('page_range', 'Page N/A')
                quote_text = quote.get('text', '')
                
                # Create reference entry HTML
                reference_html = f'<div class="reference-item">'
                reference_html += f'<strong>[{reference_counter}]</strong> '
                reference_html += f'<strong>{document_name}</strong> - {page_info}'
                
                # Add quote text if available
                if quote_text:
                    quote_preview = quote_text[:200] + "..." if len(quote_text) > 200 else quote_text
                    reference_html += f'<br><em>"{quote_preview}"</em>'
                
                reference_html += '</div>'
                references_html.append(reference_html)
                reference_counter += 1
        
        # If no references found
        if not references_html:
            references_html.append('<div class="reference-item">No references available.</div>')
        
        # Create reference section HTML with styling
        reference_section = '''
        <div style="page-break-before: always; margin-top: 30px;">
            <h2 style="font-size: 16pt; margin-bottom: 20px; border-bottom: 2px solid #333; padding-bottom: 8px;">References</h2>
            <div class="references-container">
                ''' + '\n'.join(references_html) + '''
            </div>
        </div>
        
        <style>
            .reference-item {
                margin-bottom: 12px;
                padding: 8px 0;
                font-size: 10pt;
                line-height: 1.4;
            }
            .reference-item strong {
                color: #333;
            }
            .reference-item em {
                color: #666;
                font-style: italic;
                margin-left: 20px;
                display: block;
                margin-top: 4px;
            }
            .references-container {
                margin-top: 12px;
            }
        </style>
        '''
        
        # Insert reference section before closing body tag
        if '</body>' in html_content:
            html_content = html_content.replace('</body>', reference_section + '</body>')
        else:
            # Fallback: append to end of HTML
            html_content += reference_section
        
        return html_content


# Global WeasyPrint PDF generator instance
pdf_generator = WeasyPrintPDFGenerator()
