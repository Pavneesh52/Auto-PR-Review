from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from backend.config import settings


def setup_tracing(app=None):
    provider = TracerProvider()
    
    otlp_exporter = OTLPSpanExporter(
        endpoint="http://localhost:4317",
        insecure=True,
    )
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    
    trace.set_tracer_provider(provider)
    
    if app:
        FastAPIInstrumentor.instrument_app(app)
    
    SQLAlchemyInstrumentor().instrument()
    RedisInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
    
    return trace.get_tracer(__name__)


def get_tracer(name: str):
    return trace.get_tracer(name)