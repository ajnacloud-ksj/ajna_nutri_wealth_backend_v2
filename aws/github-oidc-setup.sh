#!/bin/bash

# Setup GitHub OIDC Provider and IAM Role for GitHub Actions
# This eliminates the need for AWS access keys in GitHub secrets!

set -e

# Configuration
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
GITHUB_ORG="your-github-org"  # Replace with your GitHub org/username
GITHUB_REPO="food-app"        # Replace with your repo name
ROLE_NAME="github-actions-nutriwealth"

echo "🔐 Setting up GitHub OIDC for AWS"
echo "   Account: ${AWS_ACCOUNT_ID}"
echo "   GitHub: ${GITHUB_ORG}/${GITHUB_REPO}"
echo ""

# 1. Create OIDC Provider (if it doesn't exist)
echo "1️⃣ Creating OIDC Provider..."
OIDC_PROVIDER_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"

aws iam get-open-id-connect-provider --open-id-connect-provider-arn ${OIDC_PROVIDER_ARN} 2>/dev/null || \
aws iam create-open-id-connect-provider \
    --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com \
    --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \
    --tags Key=Purpose,Value=GitHubActions Key=Project,Value=NutriWealth

# 2. Create Trust Policy
echo "2️⃣ Creating trust policy..."
cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:${GITHUB_ORG}/${GITHUB_REPO}:*"
        }
      }
    }
  ]
}
EOF

# 3. Create IAM Role
echo "3️⃣ Creating IAM Role..."
aws iam create-role --role-name ${ROLE_NAME} \
    --assume-role-policy-document file://trust-policy.json \
    --description "GitHub Actions role for NutriWealth backend deployment" \
    --tags Key=Purpose,Value=GitHubActions Key=Project,Value=NutriWealth 2>/dev/null || \
aws iam update-assume-role-policy --role-name ${ROLE_NAME} \
    --policy-document file://trust-policy.json

# 4. Create and attach permissions policy
echo "4️⃣ Creating permissions policy..."
cat > permissions-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:CreateRepository",
        "ecr:DescribeRepositories"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "lambda:UpdateFunctionCode",
        "lambda:UpdateFunctionConfiguration",
        "lambda:GetFunction",
        "lambda:GetFunctionConfiguration",
        "lambda:CreateFunction",
        "lambda:ListVersionsByFunction",
        "lambda:PublishVersion",
        "lambda:CreateAlias",
        "lambda:UpdateAlias",
        "lambda:GetAlias",
        "lambda:GetFunctionUrlConfig",
        "lambda:CreateFunctionUrlConfig",
        "lambda:UpdateFunctionUrlConfig"
      ],
      "Resource": [
        "arn:aws:lambda:*:${AWS_ACCOUNT_ID}:function:nutriwealth-backend-*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "iam:PassRole"
      ],
      "Resource": "arn:aws:iam::${AWS_ACCOUNT_ID}:role/nutriwealth-lambda-execution-role"
    },
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:PutMetricData",
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::nutriwealth-*/*",
        "arn:aws:s3:::nutriwealth-*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:*:${AWS_ACCOUNT_ID}:nutriwealth-*"
    }
  ]
}
EOF

# Attach the policy
aws iam put-role-policy --role-name ${ROLE_NAME} \
    --policy-name GitHubActionsDeploymentPolicy \
    --policy-document file://permissions-policy.json

# 5. Output important information
echo ""
echo "✅ GitHub OIDC Setup Complete!"
echo ""
echo "📋 Add these to your GitHub repository secrets:"
echo "   AWS_ACCOUNT_ID: ${AWS_ACCOUNT_ID}"
echo ""
echo "📝 The IAM Role ARN is:"
echo "   arn:aws:iam::${AWS_ACCOUNT_ID}:role/${ROLE_NAME}"
echo ""
echo "🔧 Your GitHub workflow will use:"
echo "   role-to-assume: arn:aws:iam::${AWS_ACCOUNT_ID}:role/${ROLE_NAME}"
echo ""
echo "🎯 Benefits:"
echo "   ✅ No AWS access keys needed in GitHub"
echo "   ✅ Temporary credentials (15 min expiry)"
echo "   ✅ Automatic credential rotation"
echo "   ✅ Better security and audit trail"
echo "   ✅ Follows AWS best practices"

# Clean up
rm -f trust-policy.json permissions-policy.json