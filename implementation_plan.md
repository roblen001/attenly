# Implementation Plan: Enhanced PDF Download with References

## Overview
Remove the PDF download button from the agent execution page and enhance the report view page with a modal offering download options. Implement actual PDF generation with reference formatting that converts superscripts to square brackets and adds a reference section at the end of the PDF.

## Types
- Add new TypeScript interfaces for PDF download options and reference data
- Extend existing `ReportData` and `Quote` interfaces if needed
- Add modal state management types

## Files

### New Files:
- `frontend/src/components/report/DownloadModal.tsx` - Modal component for download options
- `frontend/src/components/report/ReferenceSection.tsx` - Component for generating reference section
- `backend/app/services/pdf_generator.py` - PDF generation service using ReportLab

### Modified Files:
- `frontend/src/pages/AgentExecution.tsx` - Remove PDF download button and functionality
- `frontend/src/pages/ReportView.tsx` - Add modal state and download logic
- `frontend/src/components/report/ReportActionsBar.tsx` - Update to trigger modal instead of direct download
- `frontend/src/utils/reportUtils.ts` - Add PDF-specific formatting for square bracket references
- `backend/app/routers/agents.py` - Add PDF download endpoint
- `backend/app/services/report_service.py` - Implement actual PDF generation
- `frontend/src/types/index.ts` - Add new interfaces for PDF options

## Functions

### New Functions:
- `generatePDFWithReferences()` - Main PDF generation function
- `formatReferencesForPDF()` - Convert quotes to reference format
- `createReferenceSection()` - Generate reference section HTML
- `DownloadModal` component functions for modal state management

### Modified Functions:
- `handleDownloadPDF()` in ReportView - Show modal instead of alert
- `generateReportHTML()` in reportUtils - Add PDF context with square brackets
- `generate_pdf_report()` in report_service - Implement actual PDF generation

## Classes

### New Classes:
- `PDFGenerator` class in backend service
- `DownloadModal` React component class

## Dependencies

### New Dependencies:
- Backend: `reportlab` for PDF generation
- Frontend: No new dependencies needed (using existing modal patterns)

## Testing
- Unit tests for PDF generation functions
- Integration tests for download modal
- E2E tests for complete download flow with both options

## Implementation Order
1. Remove PDF download button from AgentExecution page
2. Create DownloadModal component with with/without references options
3. Update ReportActionsBar to show modal
4. Implement PDF generation service backend
5. Add PDF download endpoint
6. Update reportUtils for square bracket formatting
7. Add reference section generation
8. Test complete flow
