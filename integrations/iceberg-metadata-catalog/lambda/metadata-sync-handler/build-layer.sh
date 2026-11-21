#!/bin/bash
# =============================================================================
# Build PyIceberg Lambda Layer for metadata-sync-handler
# =============================================================================
# Builds a Lambda layer containing PyIceberg with S3 Tables support and PyArrow.
#
# Output: pyiceberg-s3tables-layer.zip (ready for Lambda Layer upload)
#
# Usage:
#   ./build-layer.sh
#   aws lambda publish-layer-version \
#     --layer-name pyiceberg-s3tables \
#     --zip-file fileb://pyiceberg-s3tables-layer.zip \
#     --compatible-runtimes python3.12
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"
OUTPUT_FILE="${SCRIPT_DIR}/pyiceberg-s3tables-layer.zip"

echo "============================================="
echo " Building PyIceberg Lambda Layer"
echo "============================================="

# Clean previous build
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}/python"

# Install dependencies into layer structure
# Versions live in requirements.txt only. The platform tag below is why pyarrow is
# capped there: from pyarrow 21.0.0 the cp312 x86_64 wheels are manylinux_2_28 only,
# and a manylinux_2_28-only tag cannot resolve zstandard (a pyiceberg dependency).
echo "[1/3] Installing dependencies..."
pip install \
  --target "${BUILD_DIR}/python" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  -r "${SCRIPT_DIR}/requirements.txt"

# Remove unnecessary files to reduce layer size
echo "[2/3] Optimizing layer size..."
find "${BUILD_DIR}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "${BUILD_DIR}" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find "${BUILD_DIR}" -type d -name "test" -exec rm -rf {} + 2>/dev/null || true
find "${BUILD_DIR}" -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true
find "${BUILD_DIR}" -name "*.pyc" -delete 2>/dev/null || true

# Package
echo "[3/3] Creating zip archive..."
rm -f "${OUTPUT_FILE}"
(cd "${BUILD_DIR}" && zip -r "${OUTPUT_FILE}" python/ -x '*.pyc' '*.pyo')

# Report size
LAYER_SIZE=$(du -sh "${OUTPUT_FILE}" | cut -f1)
echo ""
echo "============================================="
echo " Layer built successfully"
echo "  Output: ${OUTPUT_FILE}"
echo "  Size:   ${LAYER_SIZE}"
echo "============================================="
echo ""
echo "Upload with:"
echo "  aws lambda publish-layer-version \\"
echo "    --layer-name pyiceberg-s3tables \\"
echo "    --zip-file fileb://${OUTPUT_FILE} \\"
echo "    --compatible-runtimes python3.12 \\"
echo "    --region ap-northeast-1"
echo ""

# Warn if too large
LAYER_BYTES=$(stat -f%z "${OUTPUT_FILE}" 2>/dev/null || stat -c%s "${OUTPUT_FILE}" 2>/dev/null)
if [ "${LAYER_BYTES}" -gt 262144000 ]; then
  echo "⚠️  WARNING: Layer exceeds 250MB unzipped limit."
  echo "   Consider using a container image deployment instead."
fi

# Clean build directory
rm -rf "${BUILD_DIR}"
