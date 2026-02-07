"""
Health check endpoints for monitoring and readiness checks
"""

from datetime import datetime, timezone
from utils.http import respond
from lib.logger import logger
import os


def check(event, context):
    """
    Basic health check endpoint
    GET /health
    """
    try:
        return respond(200, {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": os.environ.get('VERSION', '2.1.0'),
            "region": os.environ.get('AWS_REGION', 'unknown'),
            "function": os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'unknown')
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return respond(503, {"status": "unhealthy", "error": str(e)})


def ready(event, context):
    """
    Readiness check - verifies all critical dependencies
    GET /ready
    """
    checks = {}

    try:
        # Check database connectivity
        db = context.get('db')
        if db:
            try:
                # Try a simple query to verify database is accessible
                result = db.query('users', limit=1)
                checks['database'] = result.get('success', False)
            except Exception as e:
                logger.warning(f"Database check failed: {e}")
                checks['database'] = False
        else:
            checks['database'] = False

        # Check Lambda runtime
        checks['lambda'] = True  # If we're here, Lambda is working

        # Check if AI service is configured
        ai_service = context.get('ai_service')
        checks['ai_service'] = ai_service is not None

        # Check if SQS is configured
        checks['sqs'] = bool(os.environ.get('ANALYSIS_QUEUE_URL'))

        # Check if S3 bucket is configured for uploads
        checks['storage'] = bool(os.environ.get('S3_BUCKET'))

        # Determine overall readiness
        critical_checks = ['database', 'lambda']
        is_ready = all(checks.get(check, False) for check in critical_checks)

        status_code = 200 if is_ready else 503

        return respond(status_code, {
            "ready": is_ready,
            "checks": checks,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return respond(503, {
            "ready": False,
            "error": str(e),
            "checks": checks
        })


def status(event, context):
    """
    Detailed status endpoint with metrics
    GET /status
    """
    try:
        db = context.get('db')

        status_info = {
            "status": "operational",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": os.environ.get('VERSION', '2.1.0'),
            "environment": {
                "region": os.environ.get('AWS_REGION', 'unknown'),
                "function": os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'unknown'),
                "memory": os.environ.get('AWS_LAMBDA_FUNCTION_MEMORY_SIZE', 'unknown'),
                "runtime": os.environ.get('AWS_EXECUTION_ENV', 'unknown')
            }
        }

        # Add cache stats if using optimized client
        if db and hasattr(db, 'get_stats'):
            stats = db.get_stats()
            status_info['cache'] = {
                "hit_rate": f"{stats.get('cache_hit_rate', 0)*100:.1f}%",
                "total_requests": stats.get('total_requests', 0),
                "cached_responses": stats.get('cached_responses', 0)
            }

        return respond(200, status_info)

    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return respond(503, {
            "status": "degraded",
            "error": str(e)
        })