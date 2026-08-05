"""Domain exceptions for python-research-service ingest pipeline."""


class IngestError(Exception):
    """Base class for all ingest-side errors."""

    error_code: str = "INGEST_ERROR"


class AkshareUpstreamError(IngestError):
    error_code = "AKSHARE_UPSTREAM"


class TransformError(IngestError):
    error_code = "TRANSFORM_ERROR"


class WriterError(IngestError):
    error_code = "WRITER_ERROR"


class NoDataError(IngestError):
    error_code = "NO_DATA"
