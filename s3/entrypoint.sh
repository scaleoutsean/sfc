#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# Synopsis:                                                                   #
# Entrypoint script for S3 container (Versity S3 GW) in SolidFire Collector   #
#   version 2.1 and above.                                                    #
#                                                                             #
# Author: @scaleoutSean (Github)                                              #
# Repository: https://github.com/scaleoutsean/sfc                             #
# License: the Apache License Version 2.0                                     #
###############################################################################

# Environment variables should be supplied via docker-compose `environment:`.

# Provide sensible defaults so the container can run without extra envs.
ROOT_ACCESS_KEY_ID=${ROOT_ACCESS_KEY_ID:-influxdb_admin}
ROOT_SECRET_ACCESS_KEY=${ROOT_SECRET_ACCESS_KEY:-influxdb_admin_secret}
AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-${ROOT_ACCESS_KEY_ID}}
AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-${ROOT_SECRET_ACCESS_KEY}}
VGW_CERT=${VGW_CERT:-/certs/s3.crt}
VGW_KEY=${VGW_KEY:-/certs/s3.key}
VGW_PORT=${VGW_PORT:-8443}
VGW_IP=${VGW_IP:-0.0.0.0}
VGW_DATA=${VGW_DATA:-/data}

echo "Starting versitygw with: access=${ROOT_ACCESS_KEY_ID} cert=${VGW_CERT} key=${VGW_KEY} addr=${VGW_IP}:${VGW_PORT} data=${VGW_DATA}"

# If VGW_CHOWN_UID/GID are provided as numeric values, chown the data dir
# and then unset them so the versitygw binary doesn't try to parse them as
# boolean flags from the environment.
is_numeric() { printf '%s' "$1" | grep -qE '^[0-9]+$'; }

if [ -n "${VGW_CHOWN_UID:-}" ] && [ -n "${VGW_CHOWN_GID:-}" ]; then
	if is_numeric "$VGW_CHOWN_UID" && is_numeric "$VGW_CHOWN_GID"; then
		echo "Setting ownership of ${VGW_DATA} to ${VGW_CHOWN_UID}:${VGW_CHOWN_GID}"
		chown -R "${VGW_CHOWN_UID}:${VGW_CHOWN_GID}" "${VGW_DATA}" || true
		unset VGW_CHOWN_UID VGW_CHOWN_GID
	else
		# leave boolean-like values alone so versitygw can read them
		:
	fi
fi

# Check if debug logging is enabled
if [ "${DEBUG:-false}" = "true" ]; then
	DEBUG_FLAG="--debug"
else
	DEBUG_FLAG=""
fi

exec versitygw --access "$ROOT_ACCESS_KEY_ID" --secret "$ROOT_SECRET_ACCESS_KEY" \
	--cert "$VGW_CERT" --key "$VGW_KEY" --port "${VGW_IP}:${VGW_PORT}" $DEBUG_FLAG posix "$VGW_DATA"

