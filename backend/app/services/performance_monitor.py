"""
Comprehensive Performance Monitoring for Attenly File Processing Pipeline

Extends the existing chunking performance monitor to cover the entire file processing
flow from upload to report generation, providing detailed timing and bottleneck analysis.
"""

import logging
import time
import threading
import psutil
import os
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from contextlib import contextmanager
from collections import defaultdict, deque
import statistics
from functools import wraps
import json
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class OperationTiming:
    """Individual operation timing with context"""
    operation: str
    start_time: float
    end_time: float
    duration: float
    memory_start: Optional[float] = None
    memory_end: Optional[float] = None
    memory_peak: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_operation: Optional[str] = None
    
    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds"""
        return self.duration * 1000
    
    @property
    def memory_delta_mb(self) -> Optional[float]:
        """Memory change in MB"""
        if self.memory_start is not None and self.memory_end is not None:
            return self.memory_end - self.memory_start
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage"""
        result = {
            'operation': self.operation,
            'duration_ms': self.duration_ms,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'metadata': self.metadata
        }
        
        if self.memory_delta_mb is not None:
            result['memory_delta_mb'] = self.memory_delta_mb
        if self.memory_peak is not None:
            result['memory_peak_mb'] = self.memory_peak
        if self.parent_operation:
            result['parent_operation'] = self.parent_operation
            
        return result


@dataclass
class FileProcessingMetrics:
    """Comprehensive metrics for a single file processing session"""
    file_id: str
    filename: str
    file_size_bytes: int
    start_time: float
    
    # Upload and validation metrics
    upload_time: float = 0.0
    hash_calculation_time: float = 0.0
    validation_time: float = 0.0
    duplicate_check_time: float = 0.0
    
    # Document processing metrics
    classification_time: float = 0.0
    content_extraction_time: float = 0.0
    total_pages: int = 0
    
    # Chunking metrics
    l1_chunking_time: float = 0.0
    l2_chunking_time: float = 0.0
    l1_chunks_created: int = 0
    l2_chunks_created: int = 0
    
    # Vector storage metrics
    vector_storage_time: float = 0.0
    chunks_stored: int = 0
    
    # LLM processing metrics (if applicable)
    vector_search_time: float = 0.0
    llm_api_time: float = 0.0
    response_processing_time: float = 0.0
    questions_processed: int = 0
    
    # Report generation metrics (if applicable)
    template_population_time: float = 0.0
    pdf_generation_time: float = 0.0
    report_caching_time: float = 0.0
    
    # Memory metrics
    memory_start_mb: Optional[float] = None
    memory_peak_mb: Optional[float] = None
    memory_end_mb: Optional[float] = None
    
    # Status and errors
    success: bool = True
    error_message: Optional[str] = None
    bottleneck_operation: Optional[str] = None
    
    # Calculated properties
    end_time: Optional[float] = None
    
    @property
    def total_processing_time(self) -> float:
        """Total processing time from start to finish"""
        if self.end_time:
            return self.end_time - self.start_time
        return 0.0
    
    @property
    def processing_rate_mb_per_sec(self) -> float:
        """Processing rate in MB per second"""
        if self.total_processing_time > 0:
            return (self.file_size_bytes / (1024 * 1024)) / self.total_processing_time
        return 0.0
    
    @property
    def memory_used_mb(self) -> Optional[float]:
        """Total memory used during processing"""
        if self.memory_start_mb is not None and self.memory_end_mb is not None:
            return self.memory_end_mb - self.memory_start_mb
        return None
    
    def get_bottleneck_analysis(self) -> Dict[str, Any]:
        """Analyze which operations took the most time"""
        operations = {
            'upload': self.upload_time,
            'validation': self.validation_time,
            'classification': self.classification_time,
            'content_extraction': self.content_extraction_time,
            'l1_chunking': self.l1_chunking_time,
            'l2_chunking': self.l2_chunking_time,
            'vector_storage': self.vector_storage_time,
            'llm_processing': self.llm_api_time,
            'pdf_generation': self.pdf_generation_time
        }
        
        # Filter out zero times
        operations = {k: v for k, v in operations.items() if v > 0}
        
        if not operations:
            return {'bottleneck': None, 'distribution': {}}
        
        total_time = sum(operations.values())
        distribution = {k: (v / total_time * 100) for k, v in operations.items()}
        bottleneck = max(operations.keys(), key=lambda k: operations[k])
        
        return {
            'bottleneck': bottleneck,
            'bottleneck_time_ms': operations[bottleneck] * 1000,
            'bottleneck_percentage': distribution[bottleneck],
            'distribution': distribution,
            'total_measured_time': total_time
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for logging/storage"""
        result = {
            'file_id': self.file_id,
            'filename': self.filename,
            'file_size_bytes': self.file_size_bytes,
            'file_size_mb': self.file_size_bytes / (1024 * 1024),
            'start_time': self.start_time,
            'end_time': self.end_time,
            'total_processing_time': self.total_processing_time,
            'processing_rate_mb_per_sec': self.processing_rate_mb_per_sec,
            'success': self.success,
            'error_message': self.error_message,
            
            # Timing breakdown
            'upload_time_ms': self.upload_time * 1000,
            'validation_time_ms': self.validation_time * 1000,
            'classification_time_ms': self.classification_time * 1000,
            'content_extraction_time_ms': self.content_extraction_time * 1000,
            'l1_chunking_time_ms': self.l1_chunking_time * 1000,
            'l2_chunking_time_ms': self.l2_chunking_time * 1000,
            'vector_storage_time_ms': self.vector_storage_time * 1000,
            'llm_api_time_ms': self.llm_api_time * 1000,
            'pdf_generation_time_ms': self.pdf_generation_time * 1000,
            
            # Counts
            'total_pages': self.total_pages,
            'l1_chunks_created': self.l1_chunks_created,
            'l2_chunks_created': self.l2_chunks_created,
            'chunks_stored': self.chunks_stored,
            'questions_processed': self.questions_processed,
            
            # Memory
            'memory_start_mb': self.memory_start_mb,
            'memory_peak_mb': self.memory_peak_mb,
            'memory_end_mb': self.memory_end_mb,
            'memory_used_mb': self.memory_used_mb,
            
            # Analysis
            'bottleneck_analysis': self.get_bottleneck_analysis()
        }
        
        return result


class PerformanceTimer:
    """High-precision timer with memory tracking"""
    
    def __init__(self, operation: str, metadata: Optional[Dict[str, Any]] = None, 
                 track_memory: bool = True, parent_operation: Optional[str] = None):
        self.operation = operation
        self.metadata = metadata or {}
        self.track_memory = track_memory
        self.parent_operation = parent_operation
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.memory_start: Optional[float] = None
        self.memory_end: Optional[float] = None
        self.memory_peak: Optional[float] = None
        self._process = psutil.Process() if track_memory else None
    
    def start(self) -> 'PerformanceTimer':
        """Start the timer"""
        self.start_time = time.perf_counter()
        if self.track_memory and self._process:
            try:
                self.memory_start = self._process.memory_info().rss / (1024 * 1024)  # MB
                self.memory_peak = self.memory_start
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.memory_start = None
        return self
    
    def update_peak_memory(self) -> None:
        """Update peak memory usage"""
        if self.track_memory and self._process and self.memory_start is not None:
            try:
                current_memory = self._process.memory_info().rss / (1024 * 1024)
                if self.memory_peak is None or current_memory > self.memory_peak:
                    self.memory_peak = current_memory
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    
    def stop(self) -> OperationTiming:
        """Stop the timer and return result"""
        if self.start_time is None:
            raise ValueError("Timer not started")
        
        self.end_time = time.perf_counter()
        duration = self.end_time - self.start_time
        
        if self.track_memory and self._process:
            try:
                self.memory_end = self._process.memory_info().rss / (1024 * 1024)  # MB
                self.update_peak_memory()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.memory_end = None
        
        return OperationTiming(
            operation=self.operation,
            start_time=self.start_time,
            end_time=self.end_time,
            duration=duration,
            memory_start=self.memory_start,
            memory_end=self.memory_end,
            memory_peak=self.memory_peak,
            metadata=self.metadata,
            parent_operation=self.parent_operation
        )


@contextmanager
def time_operation(operation: str, metadata: Optional[Dict[str, Any]] = None, 
                  track_memory: bool = True, parent_operation: Optional[str] = None,
                  log_result: bool = True):
    """Context manager for timing operations with automatic logging"""
    timer = PerformanceTimer(operation, metadata, track_memory, parent_operation)
    timer.start()
    try:
        yield timer
    finally:
        result = timer.stop()
        
        # Log the result
        if log_result:
            memory_info = ""
            if result.memory_delta_mb is not None:
                memory_info = f" (Δmem: {result.memory_delta_mb:+.1f}MB)"
            
            logger.info(f"⏱️  {operation}: {result.duration_ms:.1f}ms{memory_info}")
        
        # Record in global monitor
        get_performance_monitor().record_operation_timing(result)


def timed_operation(operation_name: Optional[str] = None, track_memory: bool = True, 
                   log_result: bool = True, include_args: bool = False):
    """Decorator for timing function calls"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build operation name
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            
            # Build metadata
            metadata = {"function": func.__name__}
            if include_args and args:
                metadata["args_count"] = len(args)
            if include_args and kwargs:
                metadata["kwargs"] = {k: str(v)[:100] for k, v in kwargs.items()}
            
            with time_operation(op_name, metadata, track_memory, log_result=log_result):
                return func(*args, **kwargs)
        return wrapper
    return decorator


class FileProcessingPerformanceMonitor:
    """Main performance monitoring service for file processing pipeline"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self._processing_sessions: Dict[str, FileProcessingMetrics] = {}
        self._completed_sessions: deque = deque(maxlen=max_history)
        self._operation_timings: deque = deque(maxlen=max_history * 50)
        self._lock = threading.Lock()
        
        # Performance thresholds (in seconds)
        self.performance_thresholds = {
            'upload': 5.0,
            'validation': 2.0,
            'classification': 1.0,
            'content_extraction': 10.0,
            'chunking': 15.0,
            'vector_storage': 5.0,
            'llm_processing': 30.0,
            'pdf_generation': 10.0
        }
        
        # Statistics tracking
        self._operation_stats: Dict[str, List[float]] = defaultdict(list)
        self._error_counts: Dict[str, int] = defaultdict(int)
    
    def start_file_processing(self, file_id: str, filename: str, file_size_bytes: int) -> FileProcessingMetrics:
        """Start monitoring a file processing session"""
        with self._lock:
            # Get memory info
            memory_start = None
            try:
                memory_start = psutil.Process().memory_info().rss / (1024 * 1024)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            
            metrics = FileProcessingMetrics(
                file_id=file_id,
                filename=filename,
                file_size_bytes=file_size_bytes,
                start_time=time.perf_counter(),
                memory_start_mb=memory_start
            )
            
            self._processing_sessions[file_id] = metrics
            logger.info(f"📊 Started monitoring file processing: {filename} ({file_size_bytes/1024/1024:.1f}MB)")
            
            return metrics
    
    def finish_file_processing(self, file_id: str, success: bool = True, 
                              error_message: Optional[str] = None) -> Optional[FileProcessingMetrics]:
        """Finish monitoring a file processing session"""
        with self._lock:
            if file_id not in self._processing_sessions:
                logger.warning(f"No active processing session for file {file_id}")
                return None
            
            metrics = self._processing_sessions[file_id]
            metrics.end_time = time.perf_counter()
            metrics.success = success
            metrics.error_message = error_message
            
            # Update memory info
            try:
                metrics.memory_end_mb = psutil.Process().memory_info().rss / (1024 * 1024)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            
            # Analyze bottlenecks
            bottleneck_analysis = metrics.get_bottleneck_analysis()
            metrics.bottleneck_operation = bottleneck_analysis.get('bottleneck')
            
            # Move to completed sessions
            self._completed_sessions.append(metrics)
            del self._processing_sessions[file_id]
            
            # Log completion
            status = "✅ SUCCESS" if success else "❌ FAILED"
            total_time = metrics.total_processing_time
            rate = metrics.processing_rate_mb_per_sec
            
            logger.info(f"📊 {status}: {metrics.filename} processed in {total_time:.1f}s "
                       f"({rate:.1f} MB/s)")
            
            if bottleneck_analysis['bottleneck']:
                bottleneck = bottleneck_analysis['bottleneck']
                bottleneck_pct = bottleneck_analysis['bottleneck_percentage']
                logger.info(f"🐌 Bottleneck: {bottleneck} ({bottleneck_pct:.1f}% of processing time)")
            
            # Check against performance thresholds
            self._check_performance_thresholds(metrics)
            
            return metrics
    
    def record_operation_timing(self, timing: OperationTiming) -> None:
        """Record an individual operation timing"""
        with self._lock:
            self._operation_timings.append(timing)
            self._operation_stats[timing.operation].append(timing.duration)
    
    def update_file_metric(self, file_id: str, metric_name: str, value: Union[float, int]) -> None:
        """Update a specific metric for an active file processing session"""
        with self._lock:
            if file_id in self._processing_sessions:
                if hasattr(self._processing_sessions[file_id], metric_name):
                    setattr(self._processing_sessions[file_id], metric_name, value)
                else:
                    logger.warning(f"Unknown metric {metric_name} for file {file_id}")
    
    def _check_performance_thresholds(self, metrics: FileProcessingMetrics) -> None:
        """Check if any operations exceeded performance thresholds"""
        operations_to_check = {
            'upload': metrics.upload_time,
            'validation': metrics.validation_time,
            'classification': metrics.classification_time,
            'content_extraction': metrics.content_extraction_time,
            'chunking': max(metrics.l1_chunking_time, metrics.l2_chunking_time),
            'vector_storage': metrics.vector_storage_time,
            'llm_processing': metrics.llm_api_time,
            'pdf_generation': metrics.pdf_generation_time
        }
        
        for operation, actual_time in operations_to_check.items():
            threshold = self.performance_thresholds.get(operation, float('inf'))
            if actual_time > threshold:
                logger.warning(f"⚠️ Performance threshold exceeded for {operation}: "
                              f"{actual_time:.1f}s > {threshold:.1f}s (file: {metrics.filename})")
    
    def get_performance_summary(self, last_n_files: int = 100) -> Dict[str, Any]:
        """Get comprehensive performance summary"""
        with self._lock:
            recent_sessions = list(self._completed_sessions)[-last_n_files:]
            
            if not recent_sessions:
                return {"error": "No completed processing sessions found"}
            
            # Overall statistics
            successful_sessions = [s for s in recent_sessions if s.success]
            failed_sessions = [s for s in recent_sessions if not s.success]
            
            # Calculate averages
            avg_processing_time = statistics.mean(s.total_processing_time for s in successful_sessions) if successful_sessions else 0
            avg_file_size_mb = statistics.mean(s.file_size_bytes / (1024 * 1024) for s in recent_sessions)
            avg_processing_rate = statistics.mean(s.processing_rate_mb_per_sec for s in successful_sessions) if successful_sessions else 0
            
            # Bottleneck analysis
            bottleneck_counts = defaultdict(int)
            for session in successful_sessions:
                if session.bottleneck_operation:
                    bottleneck_counts[session.bottleneck_operation] += 1
            
            # Operation timing statistics
            operation_stats = {}
            for operation, timings in self._operation_stats.items():
                if timings:
                    operation_stats[operation] = {
                        "count": len(timings),
                        "mean_ms": statistics.mean(timings) * 1000,
                        "median_ms": statistics.median(timings) * 1000,
                        "min_ms": min(timings) * 1000,
                        "max_ms": max(timings) * 1000,
                        "std_dev_ms": statistics.stdev(timings) * 1000 if len(timings) > 1 else 0.0
                    }
            
            return {
                "summary": {
                    "total_files_processed": len(recent_sessions),
                    "successful_files": len(successful_sessions),
                    "failed_files": len(failed_sessions),
                    "success_rate": len(successful_sessions) / len(recent_sessions) * 100 if recent_sessions else 0,
                    "avg_processing_time_s": avg_processing_time,
                    "avg_file_size_mb": avg_file_size_mb,
                    "avg_processing_rate_mb_s": avg_processing_rate
                },
                "bottlenecks": dict(bottleneck_counts),
                "operation_statistics": operation_stats,
                "performance_thresholds": self.performance_thresholds,
                "recent_errors": [s.error_message for s in failed_sessions if s.error_message]
            }
    
    def get_file_processing_details(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed processing information for a specific file"""
        with self._lock:
            # Check active sessions first
            if file_id in self._processing_sessions:
                return {
                    "status": "processing",
                    "metrics": self._processing_sessions[file_id].to_dict()
                }
            
            # Check completed sessions
            for session in reversed(self._completed_sessions):
                if session.file_id == file_id:
                    return {
                        "status": "completed",
                        "metrics": session.to_dict()
                    }
            
            return None
    
    def log_performance_report(self, level: int = logging.INFO, last_n_files: int = 50) -> None:
        """Log a comprehensive performance report"""
        summary = self.get_performance_summary(last_n_files)
        
        if "error" in summary:
            logger.log(level, f"Performance Monitor: {summary['error']}")
            return
        
        logger.log(level, "=" * 60)
        logger.log(level, "📊 FILE PROCESSING PERFORMANCE REPORT")
        logger.log(level, "=" * 60)
        
        s = summary["summary"]
        logger.log(level, f"Files processed: {s['total_files_processed']} "
                         f"(✅ {s['successful_files']}, ❌ {s['failed_files']})")
        logger.log(level, f"Success rate: {s['success_rate']:.1f}%")
        logger.log(level, f"Average processing time: {s['avg_processing_time_s']:.1f}s")
        logger.log(level, f"Average file size: {s['avg_file_size_mb']:.1f}MB")
        logger.log(level, f"Average processing rate: {s['avg_processing_rate_mb_s']:.1f}MB/s")
        
        logger.log(level, "\n🐌 BOTTLENECK ANALYSIS:")
        for bottleneck, count in summary["bottlenecks"].items():
            percentage = count / s['successful_files'] * 100 if s['successful_files'] > 0 else 0
            logger.log(level, f"  {bottleneck}: {count} files ({percentage:.1f}%)")
        
        logger.log(level, "\n⏱️ OPERATION STATISTICS:")
        for operation, stats in summary["operation_statistics"].items():
            logger.log(level, f"  {operation}: {stats['mean_ms']:.1f}ms avg "
                             f"(min: {stats['min_ms']:.1f}ms, max: {stats['max_ms']:.1f}ms, "
                             f"count: {stats['count']})")
        
        if summary["recent_errors"]:
            logger.log(level, "\n❌ RECENT ERRORS:")
            for error in summary["recent_errors"][:5]:  # Show last 5 errors
                logger.log(level, f"  {error}")
        
        logger.log(level, "=" * 60)
    
    def build_export_data(self, last_n_files: int = 1000) -> Dict[str, Any]:
        """Build a lock-safe snapshot suitable for an authorized download."""
        with self._lock:
            recent_sessions = list(self._completed_sessions)[-last_n_files:]
            sessions = [session.to_dict() for session in recent_sessions]
            performance_thresholds = dict(self.performance_thresholds)

        # get_performance_summary() acquires the same non-reentrant lock. Call
        # it only after releasing the snapshot lock to avoid deadlocking every
        # export request.
        export_data = {
            "export_timestamp": datetime.now().isoformat(),
            "total_sessions": len(sessions),
            "sessions": sessions,
            "summary": self.get_performance_summary(last_n_files),
            "performance_thresholds": performance_thresholds,
        }

        return export_data

    def export_metrics(self, filepath: str, last_n_files: int = 1000) -> None:
        """Export performance metrics to a caller-selected JSON file."""
        export_data = self.build_export_data(last_n_files)
        sessions = export_data["sessions"]

        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)

        logger.info(f"📤 Exported {len(sessions)} processing sessions to {filepath}")


# Global performance monitor instance
_global_monitor = FileProcessingPerformanceMonitor()


def get_performance_monitor() -> FileProcessingPerformanceMonitor:
    """Get the global performance monitor instance"""
    return _global_monitor


def reset_performance_monitor() -> None:
    """Reset the global performance monitor"""
    global _global_monitor
    _global_monitor = FileProcessingPerformanceMonitor()
