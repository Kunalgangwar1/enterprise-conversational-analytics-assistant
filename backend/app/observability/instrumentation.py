"""OpenTelemetry provider/exporter lifecycle and fail-open initialization."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from app.observability.logging import configure_logging
from app.observability.metrics import ApplicationMetrics, set_metrics
from app.observability.tracing import set_tracer

logger = logging.getLogger(__name__)


@dataclass
class ObservabilityRuntime:
    """Owned telemetry providers with bounded flush/shutdown behavior."""

    tracer_provider: TracerProvider | None = None
    meter_provider: MeterProvider | None = None
    export_timeout_seconds: float = 5.0

    def force_flush(self) -> None:
        timeout_millis = int(self.export_timeout_seconds * 1_000)
        for provider in (self.tracer_provider, self.meter_provider):
            if provider is None:
                continue
            try:
                provider.force_flush(timeout_millis=timeout_millis)
            except Exception:
                logger.warning("Telemetry flush failed", extra={"outcome": "error"})

    def shutdown(self) -> None:
        self.force_flush()
        if self.tracer_provider is not None:
            try:
                # The trace SDK has no shutdown timeout argument; its batch processor/exporter
                # carry the bounded export timeout configured during initialization.
                self.tracer_provider.shutdown()
            except Exception:
                logger.warning("Telemetry shutdown failed", extra={"outcome": "error"})
        if self.meter_provider is not None:
            try:
                self.meter_provider.shutdown(
                    timeout_millis=int(self.export_timeout_seconds * 1_000)
                )
            except Exception:
                logger.warning("Telemetry shutdown failed", extra={"outcome": "error"})


def initialize_observability(
    settings: Any,
    *,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
    configure_logs: bool = True,
) -> ObservabilityRuntime:
    """Initialize optional providers; exporter failures never gate application startup."""

    if configure_logs and (settings.log_format == "json" or settings.observability_enabled):
        configure_logging(
            level=settings.log_level,
            log_format=settings.log_format,
            service=settings.service_name,
            service_version=settings.service_version,
            environment=settings.app_env,
        )
    if not settings.observability_enabled:
        set_metrics(ApplicationMetrics(None))
        set_tracer(None)
        return ObservabilityRuntime(export_timeout_seconds=settings.otel_export_timeout_seconds)

    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": settings.service_version,
            "deployment.environment.name": settings.app_env,
        }
    )
    tracer_provider: TracerProvider | None = None
    meter_provider: MeterProvider | None = None
    try:
        if settings.tracing_enabled:
            tracer_provider = TracerProvider(
                resource=resource,
                sampler=ParentBased(TraceIdRatioBased(settings.otel_trace_sample_ratio)),
            )
            resolved_span_exporter = span_exporter or _span_exporter(settings)
            if resolved_span_exporter is not None:
                tracer_provider.add_span_processor(
                    BatchSpanProcessor(
                        resolved_span_exporter,
                        max_queue_size=512,
                        max_export_batch_size=128,
                        schedule_delay_millis=2_000,
                        export_timeout_millis=int(settings.otel_export_timeout_seconds * 1_000),
                    )
                )
            set_tracer(tracer_provider.get_tracer(settings.service_name, settings.service_version))
        else:
            set_tracer(None)

        if settings.metrics_enabled:
            resolved_metric_reader = metric_reader or _metric_reader(settings)
            readers = [resolved_metric_reader] if resolved_metric_reader is not None else []
            meter_provider = MeterProvider(resource=resource, metric_readers=readers)
            set_metrics(
                ApplicationMetrics(
                    meter_provider.get_meter(settings.service_name, settings.service_version)
                )
            )
        else:
            set_metrics(ApplicationMetrics(None))
    except Exception:
        logger.warning("Telemetry initialization failed; continuing without export")
        set_metrics(ApplicationMetrics(None))
        set_tracer(None)
        tracer_provider = None
        meter_provider = None
    return ObservabilityRuntime(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        export_timeout_seconds=settings.otel_export_timeout_seconds,
    )


def _span_exporter(settings: Any) -> OTLPSpanExporter | None:
    endpoint = _signal_endpoint(settings.otel_exporter_otlp_endpoint, "traces")
    if endpoint is None:
        return None
    return OTLPSpanExporter(endpoint=endpoint, timeout=settings.otel_export_timeout_seconds)


def _metric_reader(settings: Any) -> PeriodicExportingMetricReader | None:
    endpoint = _signal_endpoint(settings.otel_exporter_otlp_endpoint, "metrics")
    if endpoint is None:
        return None
    exporter = OTLPMetricExporter(endpoint=endpoint, timeout=settings.otel_export_timeout_seconds)
    return PeriodicExportingMetricReader(
        exporter,
        export_interval_millis=30_000,
        export_timeout_millis=int(settings.otel_export_timeout_seconds * 1_000),
    )


def _signal_endpoint(base_endpoint: str | None, signal: str) -> str | None:
    if base_endpoint is None or not base_endpoint.strip():
        return None
    endpoint = base_endpoint.rstrip("/")
    return endpoint if endpoint.endswith(f"/v1/{signal}") else f"{endpoint}/v1/{signal}"
