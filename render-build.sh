#!/usr/bin/env bash
set -o errexit

uv sync --no-dev

uv run prisma generate

uv run prisma py fetch

PRISMA_CACHE="/opt/render/.cache/prisma-python/binaries"
PROJECT_BINARIES="/opt/render/project/src"

echo "Copying Prisma binaries to project directory..."
find $PRISMA_CACHE -name "prisma-query-engine-*" -exec cp {} $PROJECT_BINARIES/ \;

chmod +x $PROJECT_BINARIES/prisma-query-engine-* || true

echo "Build complete!"