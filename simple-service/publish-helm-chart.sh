#!/bin/bash

# Extract the version from Chart.yaml
CHART_VERSION=$(grep '^version:' Chart.yaml | awk '{print $2}')
CHART_NAME=$(grep '^name:' Chart.yaml | awk '{print $2}')
PACKAGE_NAME="${CHART_NAME}-${CHART_VERSION}.tgz"

helm package .
helm repo index . --url https://lespro-charts.lon1.digitaloceanspaces.com/
aws s3 cp index.yaml s3://lespro-charts/ --endpoint-url https://lon1.digitaloceanspaces.com --acl public-read
aws s3 cp "$PACKAGE_NAME" s3://lespro-charts/ --endpoint-url https://lon1.digitaloceanspaces.com --acl public-read


helm package . --version 0.1.4
mc cp ./simple-service-0.1.4.tgz myminio/roi25-engineering-helm-simple-chart/
helm repo index . --url http://192.168.68.44:9000/roi25-engineering-helm-simple-chart
mc cp ./index.yaml myminio/roi25-engineering-helm-simple-chart/

# Test:
helm template . --name-template downloader-ws --namespace downloader-ws-test \
  --set image.repository=192.168.68.45:5000/downloader-ws \
  --set image.tag=0.32.0