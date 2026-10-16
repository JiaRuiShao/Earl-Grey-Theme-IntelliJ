#!/usr/bin/env bash
# Regenerates docs/comparison.html: what VS Code paints vs what IntelliJ paints for samples/Showcase.java.
#
# Needs: JDK 21 (java + javac), Node 18+, Python 3.10+, git, and network access to download.eclipse.org + github.com.
# Optional overrides:
#   JDTLS_HOME       an unpacked Eclipse JDT Language Server (default: download 1.58.0; 1.62+ needs a Java 25 runtime)
#   EARL_GREY_THEME  path to Earl-Grey-color-theme.json (default: clone earl-grey-theme/earl-grey-vsc)
#   SCHEME           the .icls to check (default: "Earl Grey.icls")
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build"
mkdir -p "$BUILD"
SCHEME="${SCHEME:-$ROOT/Earl Grey.icls}"

clone_sparse() { # repo dir paths...
  local repo="$1" dir="$2"; shift 2
  if [ ! -d "$dir/.git" ]; then
    git clone -q --depth 1 --filter=blob:none --no-checkout "https://github.com/$repo" "$dir"
  fi
  git -C "$dir" sparse-checkout set --no-cone "$@"
  git -C "$dir" checkout -q
}

echo "==> sources"
clone_sparse redhat-developer/vscode-java "$BUILD/vscode-java" /language-support/java/java.tmLanguage.json
clone_sparse JetBrains/intellij-community "$BUILD/intellij-community" \
  /platform/platform-resources/src/DefaultColorSchemesManager.xml \
  /platform/core-api/src/com/intellij/openapi/editor/DefaultLanguageHighlighterColors.java \
  /java/java-frontback-psi-impl/src/com/intellij/ide/highlighter/JavaHighlightingColors.java
if [ -z "${EARL_GREY_THEME:-}" ]; then
  clone_sparse earl-grey-theme/earl-grey-vsc "$BUILD/earl-grey-vsc" /themes/Earl-Grey-color-theme.json
  EARL_GREY_THEME="$BUILD/earl-grey-vsc/themes/Earl-Grey-color-theme.json"
fi
if [ -z "${JDTLS_HOME:-}" ]; then
  JDTLS_HOME="$BUILD/jdtls"
  if [ ! -d "$JDTLS_HOME/plugins" ]; then
    mkdir -p "$JDTLS_HOME"
    curl -sSL https://download.eclipse.org/jdtls/milestones/1.58.0/jdt-language-server-1.58.0-202604151538.tar.gz \
      | tar xz -C "$JDTLS_HOME"
  fi
fi

echo "==> sample project for jdt.ls"
PROJECT="$BUILD/sample-project"
mkdir -p "$PROJECT/src/main/java/com/earlgrey/demo" "$PROJECT/.settings"
cp "$ROOT/samples/Showcase.java" "$PROJECT/src/main/java/com/earlgrey/demo/Showcase.java"
cat > "$PROJECT/.project" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<projectDescription><name>earlgrey-sample</name><comment></comment><projects></projects>
  <buildSpec><buildCommand><name>org.eclipse.jdt.core.javabuilder</name><arguments></arguments></buildCommand></buildSpec>
  <natures><nature>org.eclipse.jdt.core.javanature</nature></natures>
</projectDescription>
EOF
cat > "$PROJECT/.classpath" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<classpath>
  <classpathentry kind="src" path="src/main/java"/>
  <classpathentry kind="con" path="org.eclipse.jdt.launching.JRE_CONTAINER/org.eclipse.jdt.internal.debug.ui.launcher.StandardVMType/JavaSE-21"/>
  <classpathentry kind="output" path="bin"/>
</classpath>
EOF
printf 'eclipse.preferences.version=1\norg.eclipse.jdt.core.compiler.compliance=21\norg.eclipse.jdt.core.compiler.source=21\norg.eclipse.jdt.core.compiler.codegen.targetPlatform=21\n' \
  > "$PROJECT/.settings/org.eclipse.jdt.core.prefs"
SOURCE="$PROJECT/src/main/java/com/earlgrey/demo/Showcase.java"

echo "==> VS Code: semantic tokens from jdt.ls"
rm -rf "$BUILD/jdtls-data"
python3 "$ROOT/tools/vscode/lsp_client.py" "$JDTLS_HOME" "$PROJECT" "$SOURCE" "$BUILD/semtokens.json" 2>"$BUILD/lsp_client.log"

echo "==> VS Code: TextMate tokens (vscode-textmate)"
(cd "$ROOT/tools/vscode" && npm install --silent --no-audit --no-fund >/dev/null)
node "$ROOT/tools/vscode/tokenize.js" "$BUILD/vscode-java/language-support/java/java.tmLanguage.json" \
  "$EARL_GREY_THEME" "$SOURCE" "$BUILD/textmate.json"

echo "==> VS Code: resolve styles"
python3 "$ROOT/tools/vscode/vscode_render.py" "$BUILD/textmate.json" "$BUILD/semtokens.json" "$EARL_GREY_THEME" \
  "$BUILD/vscode_render.json" > "$BUILD/vscode_render.log"

echo "==> IntelliJ: highlighting"
java "$ROOT/tools/intellij/IntelliJHighlightSimulator.java" "$SOURCE" "$BUILD/intellij_spans.json"

echo "==> compare"
python3 "$ROOT/tools/compare.py" --scheme "$SCHEME" --intellij-spans "$BUILD/intellij_spans.json" \
  --vscode "$BUILD/vscode_render.json" --source "$SOURCE" --intellij-src "$BUILD/intellij-community" \
  --theme "$EARL_GREY_THEME" --out "$ROOT/docs/comparison.html" --json-out "$BUILD/comparison.json" \
  --markdown-out "$ROOT/docs/elements.md"
