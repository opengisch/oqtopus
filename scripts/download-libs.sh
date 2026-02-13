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

# Create __init__.py to make libs a package
touch oqtopus/libs/__init__.py

# set write rights to group (because qgis-plugin-ci needs it)
chmod -R g+w oqtopus/libs
