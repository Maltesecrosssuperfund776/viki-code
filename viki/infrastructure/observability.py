from .._log import structlog
import logging
import sys
from typing import Dict, Any

# Prometheus metrics (optional)
try:
    from prometheus_client import Counter, Histogram, Gauge, start_http_server
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# Prometheus metrics
if PROMETHEUS_AVAILABLE:
    swarm_counter = Counter('viki_swarm_total', 'Total swarms created', ['type', 'status'])
    api_latency = Histogram('viki_api_latency_seconds', 'API call latency', ['model'])
    cost_gauge = Gauge('viki_session_cost_usd', 'Current session cost', ['session_id'])
    token_counter = Counter('viki_tokens_total', 'Total tokens used', ['model', 'type'])
    active_agents = Gauge('viki_active_agents', 'Currently active agents')
else:
    swarm_counter = None
    api_latency = None
    cost_gauge = None
    token_counter = None
    active_agents = None

def setup_logging(log_level: str = "INFO", structured: bool = True):
    """Configure structured logging"""
    if structured:
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        # Setup standard library logging
        log_handler = logging.StreamHandler(sys.stdout)
        
        try:
            from pythonjsonlogger import jsonlogger
            formatter = jsonlogger.JsonFormatter(
                '%(timestamp)s %(level)s %(name)s %(message)s'
            )
            log_handler.setFormatter(formatter)
        except ImportError:
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
            log_handler.setFormatter(formatter)
        
        root_logger = logging.getLogger()
        root_logger.addHandler(log_handler)
        root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    else:
        logging.basicConfig(
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            level=getattr(logging, log_level.upper(), logging.INFO)
        )

def start_metrics_server(port: int = 9090):
    """Start Prometheus metrics endpoint"""
    if not PROMETHEUS_AVAILABLE:
        logging.getLogger(__name__).warning("Prometheus client not available, metrics disabled")
        return
    
    try:
        start_http_server(port)
        logging.getLogger(__name__).info(f"Metrics server started on port {port}")
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to start metrics server: {e}")

class MetricsCollector:
    def __init__(self):
        self.swarm_count = 0
        self.error_count = 0
        
    def record_swarm(self, swarm_type: str, status: str):
        if swarm_counter:
            swarm_counter.labels(type=swarm_type, status=status).inc()
        
    def record_api_call(self, model: str, latency: float, input_tokens: int, output_tokens: int):
        if api_latency:
            api_latency.labels(model=model).observe(latency)
        if token_counter:
            token_counter.labels(model=model, type="input").inc(input_tokens)
            token_counter.labels(model=model, type="output").inc(output_tokens)
        
    def update_cost(self, session_id: str, cost: float):
        if cost_gauge:
            cost_gauge.labels(session_id=session_id).set(cost)
        
    def set_active_agents(self, count: int):
        if active_agents:
            active_agents.set(count)
