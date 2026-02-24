#!/bin/bash


CHART_VERSION=$(awk '/^version:/{print $2}' Chart.yaml)
CHART_NAME=$(awk '/^name:/{print $2}' Chart.yaml)
PACKAGE_NAME="${CHART_NAME}-${CHART_VERSION}.tgz"

REPO_URL="http://192.168.68.45:9000/helm-chart"
MINIO_PATH="/helm-chart"

helm package .

curl -fsS "${REPO_URL}/index.yaml" -o index.remote.yaml
helm repo index . --url "${REPO_URL}" --merge index.remote.yaml

mc cp "./${PACKAGE_NAME}" "${MINIO_PATH}/"
mc cp ./index.yaml "${MINIO_PATH}/"

curl -fsS "${REPO_URL}/index.yaml" | grep "${PACKAGE_NAME}"
curl -fsS "${REPO_URL}/index.yaml" | grep "${PACKAGE_NAME}"
