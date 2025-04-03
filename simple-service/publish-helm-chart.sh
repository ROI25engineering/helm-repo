#!/bin/bash

# Extract the version from Chart.yaml
CHART_VERSION=$(grep '^version:' Chart.yaml | awk '{print $2}')
CHART_NAME=$(grep '^name:' Chart.yaml | awk '{print $2}')
PACKAGE_NAME="${CHART_NAME}-${CHART_VERSION}.tgz"

helm package .
helm repo index . --url https://lespro-charts.lon1.digitaloceanspaces.com/
aws s3 cp index.yaml s3://lespro-charts/ --endpoint-url https://lon1.digitaloceanspaces.com --acl public-read
aws s3 cp "$PACKAGE_NAME" s3://lespro-charts/ --endpoint-url https://lon1.digitaloceanspaces.com --acl public-read
