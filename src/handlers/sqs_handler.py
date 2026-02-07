# This file ensures SQS handling is included in Docker build
# Forces the async handler to be imported and included in the image
from handlers.analyze_async import process_sqs_messages, process_async_request
import logging

logger = logging.getLogger(__name__)
logger.info("SQS handler module loaded - ensuring async processing is available")

# Export the handlers explicitly
__all__ = ['process_sqs_messages', 'process_async_request']

def init():
    """Initialize SQS handler - called during Lambda cold start"""
    logger.info("SQS handler initialized")
    return True

# Call init to ensure module is loaded
init()