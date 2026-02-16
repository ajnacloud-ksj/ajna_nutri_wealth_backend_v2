#!/bin/bash
# Emergency fix script for Lambda deployment issues with OCI format

set -e

echo "🔧 Fixing Lambda deployment by building Docker V2 format image..."

# Configuration
AWS_REGION="ap-south-1"
ECR_REPO="nutriwealth-backend"
LAMBDA_FUNCTION="ajna_nutri_wealth_backend_v2"
AWS_ACCOUNT="808527335982"

# Get ECR login
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com

# Build image without buildx (ensures Docker V2 format)
echo "📦 Building Docker image in V2 format (not OCI)..."
DOCKER_BUILDKIT=0 docker build \
  --no-cache \
  -t $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:fix-deploy \
  -t $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest \
  .

# Push to ECR
echo "⬆️ Pushing to ECR..."
docker push $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:fix-deploy
docker push $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest

# Update Lambda
echo "🚀 Updating Lambda function..."
aws lambda update-function-code \
  --function-name $LAMBDA_FUNCTION \
  --image-uri $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:fix-deploy \
  --region $AWS_REGION

echo "✅ Deployment complete! Lambda should now be running with the fixed image."
echo "📝 Note: The function architecture will automatically match the container architecture (x86_64)."