#!/usr/bin/env bash
# Local helper: lint-check, package, upload to S3, and trigger wealth-mgmt-deploy.
# Run from the repo root. Requires AWS credentials (isengardcli or profile default).
set -euo pipefail

REGION_CB="us-west-2"
REGION_S3="ap-southeast-2"
BUCKET="wealth-management-portal-ci-i-sourcebucketddd2130a-fdrsgn16otcu"
PROJECT="wealth-mgmt-deploy"
ZIP="/tmp/wealth-mgmt-source.zip"

echo "==> Running UI compile + lint (fast CI pre-check)..."
pnpm nx run @wealth-management-portal/ui:compile
pnpm nx run @wealth-management-portal/ui:lint

echo "==> Packaging source..."
rm -f "$ZIP"
zip -r "$ZIP" . \
  --exclude "*.git*" \
  --exclude "*node_modules*" \
  --exclude "*__pycache__*" \
  --exclude "*.pyc" \
  --exclude "*/dist/*" \
  --exclude "*/.venv/*" \
  --exclude "*/coverage/*" \
  --exclude "*/reports/*" \
  2>&1 | tail -3
echo "    $(du -sh "$ZIP" | cut -f1)"

echo "==> Uploading to S3..."
aws s3 cp "$ZIP" "s3://$BUCKET/source.zip" --region "$REGION_S3"

echo "==> Starting CodeBuild..."
BUILD_ID=$(aws codebuild start-build \
  --project-name "$PROJECT" \
  --region "$REGION_CB" \
  --query 'build.id' --output text)

SHORT_ID="${BUILD_ID##*:}"
echo ""
echo "Build started: $BUILD_ID"
echo "Console: https://${REGION_CB}.console.aws.amazon.com/codesuite/codebuild/projects/${PROJECT}/build/${PROJECT}%3A${SHORT_ID}/log"
