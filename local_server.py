import os
import sys
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

## Load env vars from .env file.
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
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Api-Key, X-Tenant-ID')
        self.end_headers()

    def _invoke_lambda(self, method):
        # Construct Lambda Event
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query_params = {k: v[0] for k, v in parse_qs(parsed_path.query).items()}

        # Handle body
        body = None
        if method in ['POST', 'PUT', 'PATCH']:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                raw_body = self.rfile.read(content_length)
                try:
                    body = raw_body.decode('utf-8')
                except:
                    # If not UTF-8, might be binary (like an image)
                    import base64
                    body = base64.b64encode(raw_body).decode('utf-8')

        # Construct event
        event = {
            'httpMethod': method,
            'path': path,
            'queryStringParameters': query_params if query_params else None,
            'headers': dict(self.headers),
            'body': body,
            'isBase64Encoded': False  # We handle base64 in the body itself if needed
        }

        # Call Lambda Handler
        try:
            response = lambda_handler(event, {})

            # Send Response
            status_code = response.get('statusCode', 200)
            self.send_response(status_code)

            # Send Headers
            for header, value in response.get('headers', {}).items():
                self.send_header(header, value)
            self.end_headers()

            # Send Body
            body = response.get('body', '')
            if response.get('isBase64Encoded'):
                import base64
                body = base64.b64decode(body)
                self.wfile.write(body)
            else:
                if isinstance(body, dict):
                    body = json.dumps(body)
                self.wfile.write(body.encode('utf-8'))

        except Exception as e:
            logger.error(f"Error invoking lambda: {e}")
            import traceback
            traceback.print_exc()

            # Send error response
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            error_response = {
                'error': str(e),
                'type': type(e).__name__
            }
            self.wfile.write(json.dumps(error_response).encode('utf-8'))

    def do_GET(self):
        self._invoke_lambda('GET')

    def do_POST(self):
        self._invoke_lambda('POST')

    def do_PUT(self):
        self._invoke_lambda('PUT')

    def do_DELETE(self):
        self._invoke_lambda('DELETE')

    def do_PATCH(self):
        self._invoke_lambda('PATCH')

def run_server():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, LocalLambdaHandler)
    logger.info(f"🚀 Local Lambda Server running on port {PORT}")
    logger.info(f"   Access at: http://localhost:{PORT}")
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()
