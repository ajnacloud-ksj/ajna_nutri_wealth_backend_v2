import os
import sys
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

# Load env vars from .env file
load_dotenv()

# Configuration
PORT = int(os.environ.get('PORT', 8080))
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
sys.path.append(SRC_DIR)

# Import the Lambda Handler
try:
    from app import lambda_handler
except ImportError as e:
    print(f"Error importing app.py: {e}")
    sys.exit(1)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('LocalServer')

class LocalLambdaHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Api-Key')
        self.end_headers()

    def _invoke_lambda(self, method):
        # Construct Lambda Event
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query_params = {k: v[0] for k, v in parse_qs(parsed_path.query).items()}
        
        headers = {k: v for k, v in self.headers.items()}
        
        # Read Body
        body = None
        if method in ['POST', 'PUT', 'PATCH']:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                body = self.rfile.read(content_length).decode('utf-8')

        # Mock Authorization Context (Development Mode)
        # In production this comes from Cognito Authorizer
        auth_header = headers.get('Authorization', '')
        # If testing locally with real tokens, we might decode JWT here? 
        # For simplicity, we pass raw header or mock ID if missing.
        user_id = "local-dev-user"
        # If client sends Bearer token, we might assume it's valid for local dev or let backend validate?
        # Our backend currently checks 'claims' in 'requestContext'.
        
        event = {
            "path": path,
            "httpMethod": method,
            "headers": headers,
            "queryStringParameters": query_params,
            "body": body,
            "pathParameters": {}, # Router populates this
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": user_id,
                        "email": "dev@local.com"
                    }
                }
            }
        }
        
        # Invoke Handler
        try:
            response = lambda_handler(event, {})
        except Exception as e:
            logger.error(f"Handler Error: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return

        # Send Response
        status_code = response.get('statusCode', 200)
        self.send_response(status_code)
        
        resp_headers = response.get('headers', {})
        for k, v in resp_headers.items():
            self.send_header(k, v)
        self.end_headers()
        
        resp_body = response.get('body', '')
        if response.get('isBase64Encoded'):
             import base64
             self.wfile.write(base64.b64decode(resp_body))
        else:
             self.wfile.write(resp_body.encode('utf-8'))

    def do_GET(self):
        self._invoke_lambda('GET')

    def do_POST(self):
        self._invoke_lambda('POST')

    def do_PUT(self):
        self._invoke_lambda('PUT')
        
    def do_DELETE(self):
        self._invoke_lambda('DELETE')

def run(server_class=HTTPServer, handler_class=LocalLambdaHandler):
    server_address = ('', PORT)
    print(f"Starting Local API Server on port {PORT}...")
    print(f"Serving content from {SRC_DIR}/app.py")
    httpd = server_class(server_address, handler_class)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()
    print("Server stopped.")

if __name__ == '__main__':
    run()
