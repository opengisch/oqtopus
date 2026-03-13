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

# Generate versions.json from the downloaded wheel filenames
# Wheel filenames follow: {name}-{version}(-…).whl
echo "{" > oqtopus/libs/versions.json
first=true
for whl in temp/*.whl; do
  basename=$(basename "$whl")
  # Extract name and version from wheel filename
  name=$(echo "$basename" | sed 's/-[0-9].*//')
  version=$(echo "$basename" | sed "s/^${name}-//" | sed 's/-.*//')
  if [ "$first" = true ]; then
    first=false
  else
    echo "," >> oqtopus/libs/versions.json
  fi
  printf '  "%s": "%s"' "$name" "$version" >> oqtopus/libs/versions.json
done
echo "" >> oqtopus/libs/versions.json
echo "}" >> oqtopus/libs/versions.json

rm -rf temp

# Create __init__.py to make libs a package
touch oqtopus/libs/__init__.py

# set write rights to group (because qgis-plugin-ci needs it)
chmod -R g+w oqtopus/libs
