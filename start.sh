#!/bin/sh
# Copy static assets for standalone mode
cp -r .next/static .next/standalone/.next/static 2>/dev/null || true
cp -r public .next/standalone/public 2>/dev/null || true

# Start the server
cd .next/standalone
PORT=${PORT:-3000} node server.js
