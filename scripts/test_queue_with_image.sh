#!/bin/bash

# Test queue endpoint with base64 image
curl -X POST http://localhost:8000/v1/queue/analysis \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "description": "chicken biryani with image",
  "imageUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
}
EOF