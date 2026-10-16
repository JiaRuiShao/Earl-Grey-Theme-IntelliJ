#!/usr/bin/env bash
# Packages "Earl Grey.icls" as an installable / Marketplace-ready plugin:
#   build/earl-grey-color-scheme-<version>.jar
# The plugin only bundles the color scheme (com.intellij.bundledColorScheme), so no Gradle or IDE download is needed.
# Usage: tools/build-plugin.sh [version]   (default 1.0.0). Needs a JDK for the `jar` tool.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-1.0.0}"
STAGE="$ROOT/build/plugin"
OUT="$ROOT/build/earl-grey-color-scheme-$VERSION.jar"

rm -rf "$STAGE" && mkdir -p "$STAGE/META-INF" "$STAGE/colors"
sed "s/@VERSION@/$VERSION/g" "$ROOT/plugin/META-INF/plugin.xml" > "$STAGE/META-INF/plugin.xml"
cp "$ROOT/plugin/META-INF/pluginIcon.svg" "$STAGE/META-INF/pluginIcon.svg"
cp "$ROOT/Earl Grey.icls" "$STAGE/colors/EarlGrey.xml"
# Parity License "Notices": every copy carries the license text with its contributor and source code lines
cp "$ROOT/LICENSE-PARITY.md" "$ROOT/LICENSE-APACHE.txt" "$STAGE/META-INF/"

rm -f "$OUT"
jar --create --file "$OUT" -C "$STAGE" .
echo "$OUT"
