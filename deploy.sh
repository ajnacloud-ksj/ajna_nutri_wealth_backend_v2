#!/bin/bash

# NutriWealth Lambda Deployment Script
# Usage: ./deploy.sh [dev|staging|prod]

set -e

# Configuration
STAGE=${1:-dev}
AWS_REGION=${AWS_REGION:-us-east-1}
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="nutriwealth-backend"
FUNCTION_NAME="nutriwealth-backend-${STAGE}"
IMAGE_TAG="${STAGE}-$(git rev-parse --short HEAD)"

echo "🚀 Deploying NutriWealth Backend to Lambda"
echo "   Stage: ${STAGE}"
echo "   Region: ${AWS_REGION}"
echo "   Account: ${AWS_ACCOUNT}"
echo ""

# 1. Build Docker image
echo "📦 Building Docker image..."
docker build -t ${ECR_REPO}:${IMAGE_TAG} .

# 2. Create ECR repository if it doesn't exist
echo "🏗️ Ensuring ECR repository exists..."
aws ecr describe-repositories --repository-names ${ECR_REPO} --region ${AWS_REGION} 2>/dev/null || \
  aws ecr create-repository --repository-name ${ECR_REPO} --region ${AWS_REGION}

# 3. Login to ECR
echo "🔐 Logging into ECR..."
aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin ${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com

# 4. Tag and push image
echo "⬆️ Pushing image to ECR..."
docker tag ${ECR_REPO}:${IMAGE_TAG} \
  ${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}

docker tag ${ECR_REPO}:${IMAGE_TAG} \
  ${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${STAGE}

docker push ${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
docker push ${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${STAGE}

# 5. Update Lambda function
echo "🔄 Updating Lambda function..."
aws lambda update-function-code \
  --function-name ${FUNCTION_NAME} \
  --image-uri ${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG} \
  --region ${AWS_REGION} \
  --publish

# 6. Wait for update to complete
echo "⏳ Waiting for Lambda update to complete..."
aws lambda wait function-updated \
  --function-name ${FUNCTION_NAME} \
  --region ${AWS_REGION}

# 7. Update alias to point to new version
echo "🏷️ Updating alias..."
VERSION=$(aws lambda list-versions-by-function \
  --function-name ${FUNCTION_NAME} \
  --region ${AWS_REGION} \
  --query "Versions[-1].Version" \
  --output text)

aws lambda update-alias \
  --function-name ${FUNCTION_NAME} \
  --name ${STAGE} \
  --function-version ${VERSION} \
  --region ${AWS_REGION} 2>/dev/null || \
aws lambda create-alias \
  --function-name ${FUNCTION_NAME} \
  --name ${STAGE} \
  --function-version ${VERSION} \
  --region ${AWS_REGION}

# 8. Run smoke tests
echo "🔍 Running smoke tests..."
FUNCTION_URL=$(aws lambda get-function-url-config \
  --function-name ${FUNCTION_NAME} \
  --region ${AWS_REGION} \
  --query FunctionUrl \
  --output text 2>/dev/null || echo "No function URL")

if [ "$FUNCTION_URL" != "No function URL" ]; then
  echo "   Testing health endpoint..."
  curl -s "${FUNCTION_URL}health" || echo "Health check not available"
fi

echo ""
echo "✅ Deployment complete!"
echo "   Function: ${FUNCTION_NAME}"
echo "   Version: ${VERSION}"
echo "   Image: ${ECR_REPO}:${IMAGE_TAG}"
echo ""
echo "📊 View logs:"
echo "   aws logs tail /aws/lambda/${FUNCTION_NAME} --follow"
echo ""
echo "🔄 Rollback if needed:"
echo "   aws lambda update-alias --function-name ${FUNCTION_NAME} --name ${STAGE} --function-version \$PREV_VERSION"