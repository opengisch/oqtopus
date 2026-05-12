#!/usr/bin/env bash
set -e

# Download bundled libraries from requirements-libs.txt
while IFS= read -r line; do
  # Skip empty lines and comments
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  pip download "$line" --no-deps --only-binary :all: -d temp/
done < requirements-libs.txt

# Unzip all .whl files into oqtopus/libs
for whl in temp/*.whl; do
  unzip -o "$whl" -d oqtopus/libs
done

rm -rf temp

# Strip the body (README, examples, ...) from each bundled METADATA file.
# Only the headers (Name:, Version:, ...) are needed at runtime — the body
# can contain example connection strings like `password=...` that trigger
# false positives in the QGIS plugin repository's secret scanner.
# Per RFC 822 / PEP 566, headers and body are separated by a blank line.
for metadata in oqtopus/libs/*.dist-info/METADATA; do
  [[ -f "$metadata" ]] || continue
  awk 'BEGIN{body=0} /^$/{body=1} body==0{print}' "$metadata" > "$metadata.tmp"
  mv "$metadata.tmp" "$metadata"
done

# Create __init__.py to make libs a package
touch oqtopus/libs/__init__.py

# set write rights to group (because qgis-plugin-ci needs it)
chmod -R g+w oqtopus/libs
