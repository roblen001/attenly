"""
URL construction utilities for building application URLs.
"""
from app.config import APP_URL


def build_report_url(report_id: str) -> str:
    """
    Construct frontend URL for viewing a saved report.
    
    Args:
        report_id: Report UUID from saved_reports table
        
    Returns:
        Full URL in format: {APP_URL}/report/saved/{report_id}
        
    Example:
        >>> build_report_url("123e4567-e89b-12d3-a456-426614174000")
        'https://app.example.com/report/saved/123e4567-e89b-12d3-a456-426614174000'
    """
    return f"{APP_URL}/report/saved/{report_id}"
