"""
Default CSS for Attenly report templates.

This CSS is applied to:
1. Blank templates when no custom CSS is provided
2. Legacy agents created before the CSS feature was added
3. TinyMCE editor as content_style for consistent preview
4. PDF generation for professional document styling

The styles define a professional legal/business document appearance with:
- Calibri font family (professional and readable)
- Proper spacing and margins
- Clear section hierarchy
- Styled tables for metadata and issues
- Color-coded risk levels
- Professional signature blocks
"""

DEFAULT_TEMPLATE_CSS = """
/* Base document styles */
body {
    font-family: "Calibri", Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #333;
    background-color: #fff;
    margin: 0;
    padding: 20px;
}

/* Main template wrapper */
.report-wrapper {
    max-width: 800px;
    margin: 0 auto;
    background-color: #fff;
}

/* Header section */
.report-header {
    margin-bottom: 30px;
    padding-bottom: 15px;
    border-bottom: 2px solid #2c3e50;
}

/* Firm information block */
.firm-block {
    margin-bottom: 20px;
}

.firm-name {
    font-size: 14pt;
    font-weight: bold;
    color: #2c3e50;
    margin-bottom: 5px;
}

.firm-details {
    font-size: 10pt;
    color: #555;
    line-height: 1.4;
}

/* Report title and metadata */
.report-meta-title {
    font-size: 10pt;
    font-weight: bold;
    color: #7f8c8d;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 5px;
}

.report-title {
    font-size: 16pt;
    font-weight: bold;
    color: #2c3e50;
    margin-bottom: 5px;
}

.report-subtitle {
    font-size: 12pt;
    color: #555;
    margin-bottom: 15px;
}

/* Metadata table */
.meta-table {
    width: 100%;
    border-collapse: collapse;
    margin: 15px 0 25px 0;
    font-size: 10pt;
}

.meta-table th {
    background-color: #ecf0f1;
    text-align: left;
    padding: 8px 12px;
    font-weight: bold;
    color: #2c3e50;
    border: 1px solid #bdc3c7;
    width: 30%;
}

.meta-table td {
    padding: 8px 12px;
    border: 1px solid #bdc3c7;
    color: #333;
}

/* Content sections */
.section {
    margin-bottom: 25px;
}

.section-title {
    font-size: 13pt;
    font-weight: bold;
    color: #2c3e50;
    margin-bottom: 10px;
    margin-top: 20px;
    border-bottom: 1px solid #bdc3c7;
    padding-bottom: 5px;
}

.section-body {
    margin-bottom: 15px;
}

.section-body p {
    margin: 0 0 10px 0;
}

.section-body ul,
.section-body ol {
    margin: 10px 0;
    padding-left: 25px;
}

.section-body li {
    margin-bottom: 5px;
}

/* Callout boxes */
.callout {
    background-color: #f8f9fa;
    border-left: 4px solid #3498db;
    padding: 12px 15px;
    margin: 15px 0;
    font-size: 10pt;
}

/* Risk level indicators */
.risk-level-high {
    color: #e74c3c;
    font-weight: bold;
}

.risk-level-medium {
    color: #f39c12;
    font-weight: bold;
}

.risk-level-low {
    color: #27ae60;
    font-weight: bold;
}

/* Issues/findings table */
.issues-table {
    width: 100%;
    border-collapse: collapse;
    margin: 15px 0;
    font-size: 10pt;
}

.issues-table thead {
    background-color: #34495e;
    color: #fff;
}

.issues-table th {
    text-align: left;
    padding: 10px 12px;
    font-weight: bold;
    border: 1px solid #2c3e50;
}

.issues-table td {
    padding: 10px 12px;
    border: 1px solid #bdc3c7;
    vertical-align: top;
}

.issues-table tbody tr:nth-child(even) {
    background-color: #f8f9fa;
}

.issues-table tbody tr:hover {
    background-color: #ecf0f1;
}

/* Signature block */
.signature-block {
    margin-top: 40px;
    page-break-inside: avoid;
}

.signature-row {
    display: flex;
    justify-content: space-between;
    margin-bottom: 30px;
}

.signature {
    flex: 1;
    margin: 0 10px;
}

.signature-line {
    border-top: 1px solid #333;
    margin-bottom: 5px;
    padding-top: 30px;
}

.signature-label {
    font-size: 10pt;
    color: #555;
}

/* General text elements */
strong {
    font-weight: bold;
    color: #2c3e50;
}

em {
    font-style: italic;
}

h1, h2, h3 {
    color: #2c3e50;
    margin-top: 20px;
    margin-bottom: 10px;
}

h1 {
    font-size: 16pt;
}

h2 {
    font-size: 14pt;
}

h3 {
    font-size: 12pt;
}

hr {
    border: none;
    border-top: 1px solid #bdc3c7;
    margin: 20px 0;
}

/* Print-specific adjustments */
@media print {
    body {
        padding: 0;
    }
    
    .report-wrapper {
        max-width: 100%;
    }
    
    .section {
        page-break-inside: avoid;
    }
    
    .signature-block {
        page-break-before: auto;
    }
}
"""
