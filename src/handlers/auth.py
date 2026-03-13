import os
from utils.http import respond

def get_config(event, context):
    """
    GET /v1/auth/config
    Returns authentication configuration based on environment
    """
    auth_mode = os.environ.get('AUTH_MODE', 'local')

    if auth_mode == 'cognito':
        # Production mode with Cognito
        return respond(200, {
            "authMode": "cognito",
            "userPoolId": os.environ.get('COGNITO_USER_POOL_ID'),
            "userPoolClientId": os.environ.get('COGNITO_CLIENT_ID'),
            "region": os.environ.get('COGNITO_REGION', 'us-east-1')
        }, event=event)
    else:
        # Local development mode
        return respond(200, {
            "authMode": "local",
            "userPoolId": None,
            "userPoolClientId": None,
            "region": None,
            "message": "Using local authentication mode"
        }, event=event)

