import com.sun.source.doctree.DocCommentTree;
import com.sun.source.doctree.DocTree;
import com.sun.source.doctree.ParamTree;
import com.sun.source.doctree.ReferenceTree;
import com.sun.source.tree.AnnotationTree;
import com.sun.source.tree.AssignmentTree;
import com.sun.source.tree.CaseTree;
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.CompoundAssignmentTree;
import com.sun.source.tree.ExpressionTree;
import com.sun.source.tree.IdentifierTree;
import com.sun.source.tree.ImportTree;
import com.sun.source.tree.LambdaExpressionTree;
import com.sun.source.tree.MemberReferenceTree;
import com.sun.source.tree.MemberSelectTree;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.tree.ModifiersTree;
import com.sun.source.tree.NewClassTree;
import com.sun.source.tree.ParameterizedTypeTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.TypeParameterTree;
import com.sun.source.tree.UnaryTree;
import com.sun.source.tree.VariableTree;
import com.sun.source.tree.YieldTree;
import com.sun.source.util.DocSourcePositions;
import com.sun.source.util.DocTreePath;
import com.sun.source.util.DocTreePathScanner;
import com.sun.source.util.DocTrees;
import com.sun.source.util.JavacTask;
import com.sun.source.util.SourcePositions;
import com.sun.source.util.TreePath;
import com.sun.source.util.TreePathScanner;

import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.Modifier;
import javax.lang.model.element.NestingKind;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.VariableElement;
import javax.lang.model.util.Elements;
import javax.lang.model.util.Types;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Re-creates IntelliJ IDEA's Java highlighting for one source file, so a color scheme can be
 * checked token by token without launching the IDE.
 *
 * <p>It reproduces two layers, following the IntelliJ Community sources:
 * <ul>
 *   <li>the lexer layer ({@code JavaFileHighlighter}, {@code AbstractBasicJavaFileHighlighter},
 *       {@code JavaHighlightingLexer} with its string-escape, Javadoc and HTML sub-lexers);</li>
 *   <li>the "names" layer ({@code JavaNamesHighlightVisitor} and {@code HighlightNamesUtil}),
 *       plus the reassigned-variable, deprecation and TODO highlighting.</li>
 * </ul>
 * Symbols are resolved with javac (the Compiler Tree API) instead of IntelliJ's PSI, and every
 * decision rule mirrors the IntelliJ method named in the comment above it.
 *
 * <p>Usage: {@code java IntelliJHighlightSimulator.java <Source.java> <out.json>}
 */
public class IntelliJHighlightSimulator {

    /** One highlighted range: {@code layer} is "lexer" or "info"; keys are TextAttributesKey names. */
    record Span(int start, int end, String layer, List<String> keys, String why) {}

    private final String src;
    private final List<Span> spans = new ArrayList<>();

    IntelliJHighlightSimulator(String src) {
        this.src = src;
    }

    public static void main(String[] args) throws IOException {
        Path file = Path.of(args[0]);
        String src = Files.readString(file, StandardCharsets.UTF_8);
        IntelliJHighlightSimulator sim = new IntelliJHighlightSimulator(src);
        sim.lex();
        sim.analyze(file);
        Files.writeString(Path.of(args[1]), sim.toJson(), StandardCharsets.UTF_8);
        System.out.println("spans: " + sim.spans.size());
    }

    // =====================================================================================
    // Lexer layer
    // =====================================================================================

    private static final Set<String> HARD_KEYWORDS = Set.of(
            "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class", "const",
            "continue", "default", "do", "double", "else", "enum", "extends", "final", "finally", "float",
            "for", "goto", "if", "implements", "import", "instanceof", "int", "interface", "long", "native",
            "new", "package", "private", "protected", "public", "return", "short", "static", "strictfp",
            "super", "switch", "synchronized", "this", "throw", "throws", "transient", "try", "void",
            "volatile", "while",
            // LITERAL_BIT_SET is mapped to KEYWORD as well
            "true", "false", "null");

    /** ElementType.OPERATION_BIT_SET, longest first. ARROW, DOUBLE_COLON, AT and ELLIPSIS are not in it. */
    private static final List<String> OPERATIONS = List.of(
            ">>>=", "<<=", ">>=", ">>>", "==", "<=", ">=", "!=", "&&", "||", "++", "--", "<<", ">>",
            "+=", "-=", "*=", "/=", "&=", "|=", "^=", "%=",
            "=", ">", "<", "!", "~", "?", ":", "+", "-", "*", "/", "&", "|", "^", "%");

    private final Set<String> seen = new java.util.HashSet<>();

    private void add(int start, int end, String layer, String why, String... keys) {
        if (end > start && seen.add(start + ":" + end + ":" + layer + ":" + String.join(",", keys))) {
            spans.add(new Span(start, end, layer, List.of(keys), why));
        }
    }

    private void lex() {
        int i = 0;
        int n = src.length();
        while (i < n) {
            char c = src.charAt(i);
            if (Character.isWhitespace(c)) {
                i++;
            } else if (src.startsWith("/**", i) && !src.startsWith("/**/", i)) {
                int end = src.indexOf("*/", i + 3);
                end = end < 0 ? n : end + 2;
                lexDocComment(i, end);
                lexTodo(i, end);
                i = end;
            } else if (src.startsWith("/*", i)) {
                int end = src.indexOf("*/", i + 2);
                end = end < 0 ? n : end + 2;
                add(i, end, "lexer", "C_STYLE_COMMENT", "JAVA_BLOCK_COMMENT");
                lexTodo(i, end);
                i = end;
            } else if (src.startsWith("//", i)) {
                int end = src.indexOf('\n', i);
                end = end < 0 ? n : end;
                add(i, end, "lexer", "END_OF_LINE_COMMENT", "JAVA_LINE_COMMENT");
                lexTodo(i, end);
                i = end;
            } else if (src.startsWith("\"\"\"", i)) {
                int end = src.indexOf("\"\"\"", i + 3);
                while (end > 0 && src.charAt(end - 1) == '\\') {
                    end = src.indexOf("\"\"\"", end + 1);
                }
                end = end < 0 ? n : end + 3;
                add(i, end, "lexer", "TEXT_BLOCK_LITERAL", "JAVA_STRING");
                lexEscapes(i + 3, end - 3);
                i = end;
            } else if (c == '"' || c == '\'') {
                int j = i + 1;
                while (j < n && src.charAt(j) != c && src.charAt(j) != '\n') {
                    j += src.charAt(j) == '\\' ? 2 : 1;
                }
                int end = Math.min(j + 1, n);
                add(i, end, "lexer", c == '"' ? "STRING_LITERAL" : "CHARACTER_LITERAL", "JAVA_STRING");
                lexEscapes(i + 1, end - 1);
                i = end;
            } else if (Character.isDigit(c) || (c == '.' && i + 1 < n && Character.isDigit(src.charAt(i + 1)))) {
                Matcher m = Pattern.compile(
                        "0[xX][0-9a-fA-F_]+[lL]?|0[bB][01_]+[lL]?|(\\d[\\d_]*)?\\.?\\d[\\d_]*([eE][+-]?\\d+)?[fFdDlL]?")
                        .matcher(src).region(i, n);
                int end = m.lookingAt() ? m.end() : i + 1;
                add(i, end, "lexer", "NUMBER_LITERAL", "JAVA_NUMBER");
                i = end;
            } else if (Character.isJavaIdentifierStart(c)) {
                int j = i;
                while (j < n && Character.isJavaIdentifierPart(src.charAt(j))) {
                    j++;
                }
                String word = src.substring(i, j);
                if (word.equals("non") && src.startsWith("-sealed", j)) {
                    add(i, j + 7, "lexer", "NON_SEALED_KEYWORD", "JAVA_KEYWORD");
                    j += 7;
                } else if (HARD_KEYWORDS.contains(word)) {
                    add(i, j, "lexer", "KEYWORD " + word, "JAVA_KEYWORD");
                }
                i = j;
            } else if (src.startsWith("->", i) || src.startsWith("::", i)) {
                i += 2; // ARROW / DOUBLE_COLON: no attributes key in JavaFileHighlighter
            } else if (src.startsWith("...", i)) {
                i += 3; // ELLIPSIS: no attributes key
            } else if (c == '@') {
                i++;    // AT: no attributes key
            } else {
                String key = switch (c) {
                    case '(', ')' -> "JAVA_PARENTH";
                    case '{', '}' -> "JAVA_BRACES";
                    case '[', ']' -> "JAVA_BRACKETS";
                    case ',' -> "JAVA_COMMA";
                    case '.' -> "JAVA_DOT";
                    case ';' -> "JAVA_SEMICOLON";
                    default -> null;
                };
                if (key != null) {
                    add(i, i + 1, "lexer", "punctuation", key);
                    i++;
                    continue;
                }
                final int at = i;
                String op = OPERATIONS.stream().filter(o -> src.startsWith(o, at)).findFirst().orElse(null);
                if (op != null) {
                    add(i, i + op.length(), "lexer", "operation " + op, "JAVA_OPERATION_SIGN");
                    i += op.length();
                } else {
                    i++;
                }
            }
        }
    }

    /** JavaStringLiteralLexer: escapes inside string/char/text-block literals. */
    private void lexEscapes(int from, int to) {
        for (int i = from; i < to; i++) {
            if (src.charAt(i) != '\\' || i + 1 >= to) {
                continue;
            }
            char e = src.charAt(i + 1);
            int len;
            if (e == 'u') {
                int j = i + 1;
                while (j < to && src.charAt(j) == 'u') {
                    j++;
                }
                len = (j + 4 <= to && src.substring(j, j + 4).matches("[0-9a-fA-F]{4}")) ? j + 4 - i : -1;
            } else if ("btnfrs\"'\\\n".indexOf(e) >= 0) {
                len = 2;
            } else if (e >= '0' && e <= '7') {
                int j = i + 1;
                while (j < to && j < i + 4 && src.charAt(j) >= '0' && src.charAt(j) <= '7') {
                    j++;
                }
                len = j - i;
            } else {
                len = -1;
            }
            if (len > 0) {
                add(i, i + len, "lexer", "VALID_STRING_ESCAPE_TOKEN", "JAVA_STRING", "JAVA_VALID_STRING_ESCAPE");
                i += len - 1;
            } else {
                add(i, i + 2, "lexer", "INVALID_CHARACTER_ESCAPE_TOKEN", "JAVA_STRING", "JAVA_INVALID_STRING_ESCAPE");
                i++;
            }
        }
    }

    /** JavaDocLexer + HtmlLexer layer: everything is JAVA_DOC_COMMENT, tag names add JAVA_DOC_TAG, HTML adds JAVA_DOC_MARKUP. */
    private void lexDocComment(int start, int end) {
        add(start, end, "lexer", "DOC_COMMENT", "JAVA_DOC_COMMENT");
        Matcher tag = Pattern.compile("(?<=[\\s*{])@[a-zA-Z]+").matcher(src).region(start, end);
        while (tag.find()) {
            add(tag.start(), tag.end(), "lexer", "DOC_TAG_NAME", "JAVA_DOC_COMMENT", "JAVA_DOC_TAG");
        }
        // "@param <T>" is a tag value (DOC_TAG_VALUE_LT/GT), not HTML
        Matcher html = Pattern.compile("(?<!@param )</?[a-zA-Z][a-zA-Z0-9]*[^>]*>").matcher(src).region(start, end);
        while (html.find()) {
            add(html.start(), html.end(), "lexer", "XML_TAG (javadoc markup)", "JAVA_DOC_COMMENT", "JAVA_DOC_MARKUP");
        }
    }

    /** TodoConfiguration default pattern "\btodo\b.*" (case-insensitive), highlighted inside comments. */
    private void lexTodo(int start, int end) {
        Matcher m = Pattern.compile("(?i)\\btodo\\b[^\\n]*").matcher(src).region(start, end);
        while (m.find()) {
            int e = m.end();
            String hit = src.substring(m.start(), e);
            if (hit.endsWith("*/")) {
                e -= 2;
            }
            add(m.start(), e, "info", "TODO pattern", "TODO_DEFAULT_ATTRIBUTES");
        }
    }

    // =====================================================================================
    // Names layer (JavaNamesHighlightVisitor / HighlightNamesUtil)
    // =====================================================================================

    private JavacTask task;
    private Trees2 trees;
    private Elements elements;
    private Types types;
    private CompilationUnitTree cu;
    private final Map<Element, TreePath> declarations = new HashMap<>();
    private final Map<Element, Integer> writes = new HashMap<>();
    private final Set<Tree> claimed = Collections.newSetFromMap(new IdentityHashMap<>());

    /** Small facade over DocTrees so the rest of the code reads naturally. */
    record Trees2(DocTrees api, SourcePositions positions, DocSourcePositions docPositions) {
        Element element(TreePath p) {
            return api.getElement(p);
        }
    }

    private void analyze(Path file) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        StandardJavaFileManager fm = compiler.getStandardFileManager(null, null, StandardCharsets.UTF_8);
        Iterable<? extends JavaFileObject> units = fm.getJavaFileObjects(file);
        task = (JavacTask) compiler.getTask(null, fm, d -> { }, List.of("--release", "21", "-proc:none"), null, units);
        cu = task.parse().iterator().next();
        task.analyze();
        DocTrees docTrees = DocTrees.instance(task);
        trees = new Trees2(docTrees, docTrees.getSourcePositions(), docTrees.getSourcePositions());
        elements = task.getElements();
        types = task.getTypes();

        new WriteCounter().scan(cu, null);
        new NamesVisitor().scan(cu, null);
    }

    private int start(Tree t) {
        return (int) trees.positions().getStartPosition(cu, t);
    }

    private int end(Tree t) {
        return (int) trees.positions().getEndPosition(cu, t);
    }

    /** Counts assignments so ReassignedVariableInspection can be mirrored. */
    private class WriteCounter extends TreePathScanner<Void, Void> {
        @Override
        public Void visitVariable(VariableTree node, Void unused) {
            Element e = trees.element(getCurrentPath());
            if (e != null && node.getInitializer() != null) {
                writes.merge(e, 1, Integer::sum);
            }
            return super.visitVariable(node, unused);
        }

        @Override
        public Void visitAssignment(AssignmentTree node, Void unused) {
            count(node.getVariable());
            return super.visitAssignment(node, unused);
        }

        @Override
        public Void visitCompoundAssignment(CompoundAssignmentTree node, Void unused) {
            count(node.getVariable());
            return super.visitCompoundAssignment(node, unused);
        }

        @Override
        public Void visitUnary(UnaryTree node, Void unused) {
            switch (node.getKind()) {
                case PREFIX_INCREMENT, PREFIX_DECREMENT, POSTFIX_INCREMENT, POSTFIX_DECREMENT -> count(node.getExpression());
                default -> { }
            }
            return super.visitUnary(node, unused);
        }

        private void count(ExpressionTree target) {
            Element e = trees.element(new TreePath(getCurrentPath(), target));
            if (e != null) {
                writes.merge(e, 1, Integer::sum);
            }
        }
    }

    private class NamesVisitor extends TreePathScanner<Void, Void> {

        // ----- package / imports ------------------------------------------------------

        @Override
        public Void visitCompilationUnit(CompilationUnitTree node, Void unused) {
            if (node.getPackageName() != null) {
                highlightPackageChain(node.getPackageName());
                claimAll(node.getPackageName());
            }
            return super.visitCompilationUnit(node, unused);
        }

        @Override
        public Void visitImport(ImportTree node, Void unused) {
            MemberSelectTree q = (MemberSelectTree) node.getQualifiedIdentifier();
            TreePath qPath = new TreePath(getCurrentPath(), q);
            if (node.isStatic()) {
                // visitImportStaticReferenceElement: the member, then the qualifier as an ordinary reference
                TypeElement owner = (TypeElement) trees.element(new TreePath(qPath, q.getExpression()));
                String name = q.getIdentifier().toString();
                int s = end(q) - name.length();
                for (Element member : elements.getAllMembers(owner)) {
                    if (member.getSimpleName().contentEquals(name)) {
                        if (member instanceof VariableElement v) {
                            add(s, end(q), "info", "static import of field", variableKey(v, false, null));
                        } else if (member instanceof ExecutableElement m) {
                            add(s, end(q), "info", "static import of method", methodKey(m, false, false, false));
                        } else if (member instanceof TypeElement t) {
                            add(s, end(q), "info", "static import of type", classKey(t, false));
                        }
                        break;
                    }
                }
                highlightQualified(new TreePath(qPath, q.getExpression()));
            } else {
                highlightQualified(qPath);
            }
            claimAll(q);
            return null;
        }

        private void highlightQualified(TreePath path) {
            Tree t = path.getLeaf();
            if (t instanceof MemberSelectTree ms) {
                highlightQualified(new TreePath(path, ms.getExpression()));
                String name = ms.getIdentifier().toString();
                if (!name.equals("*")) {
                    classifyReference(path, end(ms) - name.length(), end(ms));
                }
            } else if (t instanceof IdentifierTree) {
                classifyReference(path, start(t), end(t));
            }
        }

        private void highlightPackageChain(ExpressionTree name) {
            if (name instanceof MemberSelectTree ms) {
                highlightPackageChain(ms.getExpression());
                String id = ms.getIdentifier().toString();
                highlightPackage(end(ms) - id.length(), end(ms));
            } else {
                highlightPackage(start(name), end(name));
            }
        }

        // ----- declarations (visitIdentifier: parent is PsiVariable / PsiClass / PsiMethod) ----------

        @Override
        public Void visitClass(ClassTree node, Void unused) {
            TypeElement type = (TypeElement) trees.element(getCurrentPath());
            if (type != null && type.getNestingKind() != NestingKind.ANONYMOUS) {
                Matcher m = Pattern.compile("\\b(class|interface|enum|record)\\s+(" + node.getSimpleName() + ")\\b")
                        .matcher(src).region(start(node), end(node));
                if (m.find()) {
                    add(m.start(2), m.end(2), "info", "class declaration", classKey(type, false));
                    if (m.group(1).equals("record")) {
                        add(m.start(1), m.end(1), "info", "soft keyword record", "JAVA_KEYWORD");
                    }
                    String header = src.substring(start(node), m.start(1));
                    softKeyword(start(node), header, "sealed");
                    int bodyStart = src.indexOf('{', m.end(2));
                    softKeyword(m.end(2), src.substring(m.end(2), bodyStart), "permits");
                }
            }
            return super.visitClass(node, unused);
        }

        private void softKeyword(int offset, String text, String word) {
            Matcher k = Pattern.compile("(?<![-\\w])" + word + "\\b").matcher(text);
            while (k.find()) {
                add(offset + k.start(), offset + k.end(), "info", "soft keyword " + word, "JAVA_KEYWORD");
            }
        }

        @Override
        public Void visitTypeParameter(TypeParameterTree node, Void unused) {
            int s = start(node);
            add(s, s + node.getName().length(), "info", "type parameter declaration", "TYPE_PARAMETER_NAME_ATTRIBUTES");
            return super.visitTypeParameter(node, unused);
        }

        @Override
        public Void visitMethod(MethodTree node, Void unused) {
            ExecutableElement m = (ExecutableElement) trees.element(getCurrentPath());
            if (m != null && elements.getOrigin(m) == Elements.Origin.EXPLICIT) {
                String name = m.getKind() == ElementKind.CONSTRUCTOR
                        ? m.getEnclosingElement().getSimpleName().toString()
                        : node.getName().toString();
                int from = start(node);
                for (Tree t : List.of(node.getModifiers())) {
                    from = Math.max(from, end(t));
                }
                if (node.getReturnType() != null) {
                    from = Math.max(from, end(node.getReturnType()));
                }
                Matcher mm = Pattern.compile("\\b" + name + "\\s*[({]").matcher(src).region(from, end(node));
                if (mm.find()) {
                    add(mm.start(), mm.start() + name.length(), "info", "method declaration", methodKey(m, true, false, false));
                }
            }
            return super.visitMethod(node, unused);
        }

        @Override
        public Void visitVariable(VariableTree node, Void unused) {
            Element e = trees.element(getCurrentPath());
            if (e instanceof VariableElement v && isGeneratedParameter(v)) {
                // parameters of compiler-provided constructors (record canonical, anonymous class) are not in the source
                return super.visitVariable(node, unused);
            }
            if (e instanceof VariableElement v) {
                declarations.put(v, getCurrentPath());
                String name = node.getName().toString();
                int s;
                if (v.getKind() == ElementKind.ENUM_CONSTANT) {
                    s = start(node);
                    if (node.getInitializer() instanceof NewClassTree synthetic) {
                        claimed.add(synthetic.getIdentifier()); // synthetic "new Planet(...)"; its body is real code
                    }
                } else if (start(node) < 0) {
                    s = -1; // compiler-generated (e.g. implicit record fields without a position)
                } else if (end(node) < start(node)) {
                    // record header components carry a start but no end position
                    Matcher first = Pattern.compile("\\b" + Pattern.quote(name) + "\\b").matcher(src).region(start(node), src.length());
                    s = first.find() ? first.start() : -1;
                } else {
                    int to = node.getInitializer() != null ? start(node.getInitializer()) : end(node);
                    s = lastWord(name, start(node), to);
                    // "var" in a local declaration is a soft keyword (visitKeyword)
                    Matcher var = Pattern.compile("(?:final\\s+)?(var)\\s+" + name + "\\b").matcher(src).region(start(node), to);
                    if (var.lookingAt()) {
                        add(var.start(1), var.end(1), "info", "soft keyword var", "JAVA_KEYWORD");
                    }
                }
                if (s >= 0) {
                    add(s, s + name.length(), "info", "variable declaration", variableKey(v, false, getCurrentPath()));
                    reassigned(v, s, s + name.length());
                }
            }
            return super.visitVariable(node, unused);
        }

        @Override
        public Void visitYield(YieldTree node, Void unused) {
            add(start(node), start(node) + 5, "info", "soft keyword yield", "JAVA_KEYWORD");
            return super.visitYield(node, unused);
        }

        @Override
        public Void visitCase(CaseTree node, Void unused) {
            if (node.getGuard() != null) {
                int g = start(node.getGuard());
                int w = src.lastIndexOf("when", g);
                add(w, w + 4, "info", "soft keyword when", "JAVA_KEYWORD");
            }
            return super.visitCase(node, unused);
        }

        // ----- references ----------------------------------------------------------------

        @Override
        public Void visitIdentifier(IdentifierTree node, Void unused) {
            if (!claimed.contains(node)) {
                String n = node.getName().toString();
                if (!n.equals("this") && !n.equals("super")) {
                    classifyReference(getCurrentPath(), start(node), end(node));
                }
            }
            return super.visitIdentifier(node, unused);
        }

        @Override
        public Void visitMemberSelect(MemberSelectTree node, Void unused) {
            if (!claimed.contains(node)) {
                String n = node.getIdentifier().toString();
                if (!n.equals("class") && !n.equals("this") && !n.equals("super")) {
                    classifyReference(getCurrentPath(), end(node) - n.length(), end(node));
                }
            }
            return super.visitMemberSelect(node, unused);
        }

        @Override
        public Void visitMemberReference(MemberReferenceTree node, Void unused) {
            // visitMethodReferenceExpression: constructor references ("::new") get no name highlight
            if (!node.getName().contentEquals("<init>")) {
                Element e = trees.element(getCurrentPath());
                if (e instanceof ExecutableElement m) {
                    int s = end(node) - node.getName().length();
                    add(s, end(node), "info", "method reference", methodKey(m, false, calledOnThis(getCurrentPath()), false,
                            getCurrentPath()));
                }
            }
            return super.visitMemberReference(node, unused);
        }

        @Override
        public Void visitNewClass(NewClassTree node, Void unused) {
            Tree id = node.getIdentifier();
            Tree nameTree = id instanceof ParameterizedTypeTree p ? p.getType() : id;
            String text = nameTree instanceof MemberSelectTree ms ? ms.getIdentifier().toString()
                    : nameTree instanceof IdentifierTree it ? it.getName().toString() : null;
            int s = end(nameTree) - (text == null ? 0 : text.length());
            if (text != null && s >= 0 && src.startsWith(text, s)) { // enum constants carry a synthetic NewClass
                claimed.add(nameTree);
                if (node.getClassBody() != null) {
                    // reference whose parent is PsiAnonymousClass -> ANONYMOUS_CLASS_NAME
                    add(s, end(nameTree), "info", "anonymous class base", "ANONYMOUS_CLASS_NAME_ATTRIBUTES");
                } else {
                    // parent is PsiConstructorCall -> highlightMethodName(constructor) -> CONSTRUCTOR_CALL
                    add(s, end(nameTree), "info", "constructor call", "CONSTRUCTOR_CALL_ATTRIBUTES");
                }
                deprecated(trees.element(getCurrentPath()), s, end(nameTree));
            }
            return super.visitNewClass(node, unused);
        }

        @Override
        public Void visitAnnotation(AnnotationTree node, Void unused) {
            Tree type = node.getAnnotationType();
            claimed.add(type);
            Element e = trees.element(new TreePath(getCurrentPath(), type));
            // highlightClassName: the range starts at '@'
            add(start(node), end(type), "info", "annotation", e instanceof TypeElement t ? classKey(t, false) : "ANNOTATION_NAME_ATTRIBUTES");
            if (type instanceof MemberSelectTree ms) {
                highlightQualified(new TreePath(new TreePath(getCurrentPath(), type), ms.getExpression()));
            }
            for (ExpressionTree arg : node.getArguments()) {
                if (arg instanceof AssignmentTree a && a.getVariable() instanceof IdentifierTree name) {
                    claimed.add(name);
                    add(start(name), end(name), "info", "annotation attribute name", "ANNOTATION_ATTRIBUTE_NAME_ATTRIBUTES");
                }
            }
            return super.visitAnnotation(node, unused);
        }

        /** JavaNamesHighlightVisitor.doVisitReferenceElement + highlightReferencedMethodOrClassName. */
        private void classifyReference(TreePath path, int s, int e) {
            Element el = trees.element(path);
            if (el == null || s < 0) {
                return;
            }
            Tree parent = path.getParentPath().getLeaf();
            switch (el.getKind()) {
                case PACKAGE -> highlightPackage(s, e);
                case FIELD, ENUM_CONSTANT, LOCAL_VARIABLE, PARAMETER, EXCEPTION_PARAMETER, RESOURCE_VARIABLE,
                     BINDING_VARIABLE, RECORD_COMPONENT -> {
                    VariableElement v = (VariableElement) el;
                    if (isLocalish(v) && capturedByAnonymousOrLambda(path, v)) {
                        add(s, e, "info", "captured by lambda/anonymous class", "IMPLICIT_ANONYMOUS_CLASS_PARAMETER_ATTRIBUTES");
                        return;
                    }
                    add(s, e, "info", "variable reference", variableKey(v, isStaticallyImported(path, v), declarations.get(v)));
                    reassigned(v, s, e);
                    deprecated(v, s, e);
                }
                case METHOD, CONSTRUCTOR -> {
                    if (parent instanceof MethodInvocationTree) {
                        ExecutableElement m = (ExecutableElement) el;
                        add(s, e, "info", "method call",
                                methodKey(m, false, calledOnThis(path), isStaticallyImported(path, m), path));
                        deprecated(m, s, e);
                    }
                }
                case CLASS, INTERFACE, ENUM, RECORD, ANNOTATION_TYPE, TYPE_PARAMETER -> {
                    if (el.getKind() == ElementKind.TYPE_PARAMETER) {
                        add(s, e, "info", "type parameter reference", "TYPE_PARAMETER_NAME_ATTRIBUTES");
                    } else {
                        add(s, e, "info", "class reference", classKey((TypeElement) el, false));
                        deprecated(el, s, e);
                    }
                }
                default -> { }
            }
        }

        private void claimAll(Tree t) {
            new TreePathScanner<Void, Void>() {
                @Override
                public Void scan(Tree tree, Void unused) {
                    if (tree != null) {
                        claimed.add(tree);
                    }
                    return super.scan(tree, unused);
                }
            }.scan(new TreePath(getCurrentPath(), t), null);
        }

        private int lastWord(String word, int from, int to) {
            Matcher m = Pattern.compile("\\b" + Pattern.quote(word) + "\\b").matcher(src).region(from, to);
            int found = -1;
            while (m.find()) {
                found = m.start();
            }
            return found;
        }
    }

    // ----- classification rules ------------------------------------------------------------

    /** HighlightNamesUtil.highlightPackage: package segment plus the following dot, as CLASS_NAME. */
    private void highlightPackage(int s, int e) {
        int end = e < src.length() && src.charAt(e) == '.' ? e + 1 : e;
        add(s, end, "info", "package", "CLASS_NAME_ATTRIBUTES");
    }

    /** HighlightNamesUtil.getClassNameHighlightType */
    private String classKey(TypeElement t, boolean anonymousBase) {
        if (anonymousBase) {
            return "ANONYMOUS_CLASS_NAME_ATTRIBUTES";
        }
        return switch (t.getKind()) {
            case ANNOTATION_TYPE -> "ANNOTATION_NAME_ATTRIBUTES";
            case INTERFACE -> "INTERFACE_NAME_ATTRIBUTES";
            case ENUM -> "ENUM_NAME_ATTRIBUTES";
            case RECORD -> "RECORD_NAME_ATTRIBUTES";
            default -> t.getModifiers().contains(Modifier.ABSTRACT) ? "ABSTRACT_CLASS_NAME_ATTRIBUTES" : "CLASS_NAME_ATTRIBUTES";
        };
    }

    /** HighlightNamesUtil.getVariableNameHighlightType */
    private String variableKey(VariableElement v, boolean staticallyImported, TreePath declaration) {
        switch (v.getKind()) {
            case LOCAL_VARIABLE, RESOURCE_VARIABLE:
                return "LOCAL_VARIABLE_ATTRIBUTES";
            case RECORD_COMPONENT:
                return "RECORD_COMPONENT_ATTRIBUTES";
            case FIELD, ENUM_CONSTANT: {
                Set<Modifier> mods = v.getModifiers();
                if (v.getEnclosingElement().getKind() == ElementKind.RECORD && !mods.contains(Modifier.STATIC)) {
                    return "RECORD_COMPONENT_ATTRIBUTES"; // implicit record field = LightRecordField
                }
                boolean isStatic = mods.contains(Modifier.STATIC) || v.getEnclosingElement().getKind().isInterface();
                boolean isFinal = mods.contains(Modifier.FINAL) || v.getEnclosingElement().getKind().isInterface()
                                  || v.getKind() == ElementKind.ENUM_CONSTANT;
                if (isStatic) {
                    if (isFinal) {
                        return staticallyImported ? "STATIC_FINAL_FIELD_IMPORTED_ATTRIBUTES" : "STATIC_FINAL_FIELD_ATTRIBUTES";
                    }
                    return staticallyImported ? "STATIC_FIELD_IMPORTED_ATTRIBUTES" : "STATIC_FIELD_ATTRIBUTES";
                }
                return isFinal ? "INSTANCE_FINAL_FIELD_ATTRIBUTES" : "INSTANCE_FIELD_ATTRIBUTES";
            }
            default: // PARAMETER, EXCEPTION_PARAMETER, BINDING_VARIABLE (PsiPatternVariable is a PsiParameter)
                if (declaration != null && declaration.getParentPath().getLeaf() instanceof LambdaExpressionTree) {
                    return "LAMBDA_PARAMETER_ATTRIBUTES";
                }
                return "PARAMETER_ATTRIBUTES";
        }
    }

    /** HighlightNamesUtil.getMethodNameHighlightType */
    private String methodKey(ExecutableElement m, boolean declaration, boolean calledOnThis, boolean staticallyImported) {
        return methodKey(m, declaration, calledOnThis, staticallyImported, null);
    }

    private String methodKey(ExecutableElement m, boolean declaration, boolean calledOnThis, boolean staticallyImported, TreePath at) {
        if (m.getKind() == ElementKind.CONSTRUCTOR) {
            return declaration ? "CONSTRUCTOR_DECLARATION_ATTRIBUTES" : "CONSTRUCTOR_CALL_ATTRIBUTES";
        }
        if (declaration) {
            return "METHOD_DECLARATION_ATTRIBUTES";
        }
        if (m.getModifiers().contains(Modifier.STATIC)) {
            return staticallyImported ? "STATIC_METHOD_IMPORTED_ATTRIBUTES" : "STATIC_METHOD_ATTRIBUTES";
        }
        if (calledOnThis && at != null && isInherited(m, at)) {
            return "INHERITED_METHOD_ATTRIBUTES";
        }
        if (m.getModifiers().contains(Modifier.ABSTRACT)) {
            return "ABSTRACT_METHOD_ATTRIBUTES";
        }
        return "METHOD_CALL_ATTRIBUTES";
    }

    /** HighlightNamesUtil.isCalledOnThis: the nearest enclosing call has no qualifier or a "this" qualifier. */
    private boolean calledOnThis(TreePath path) {
        for (TreePath p = path.getParentPath(); p != null; p = p.getParentPath()) {
            if (p.getLeaf() instanceof MethodInvocationTree call) {
                ExpressionTree select = call.getMethodSelect();
                if (select instanceof IdentifierTree) {
                    return true;
                }
                return select instanceof MemberSelectTree ms && ms.getExpression() instanceof IdentifierTree q
                       && q.getName().contentEquals("this");
            }
        }
        return false;
    }

    /** highlightMethodName: walk enclosing classes, PsiClass.isInheritor(containingClass, true). */
    private boolean isInherited(ExecutableElement m, TreePath at) {
        TypeElement containing = (TypeElement) m.getEnclosingElement();
        for (TreePath p = at; p != null; p = p.getParentPath()) {
            if (p.getLeaf() instanceof ClassTree) {
                TypeElement enclosing = (TypeElement) trees.element(p);
                if (enclosing != null && !enclosing.equals(containing)
                    && types.isSubtype(types.erasure(enclosing.asType()), types.erasure(containing.asType()))) {
                    return true;
                }
            }
        }
        return false;
    }

    /** isStaticallyImported: an unqualified reference to a static member that no enclosing class provides. */
    private boolean isStaticallyImported(TreePath path, Element member) {
        if (!(path.getLeaf() instanceof IdentifierTree) || !member.getModifiers().contains(Modifier.STATIC)) {
            return false;
        }
        for (TreePath p = path; p != null; p = p.getParentPath()) {
            if (p.getLeaf() instanceof ClassTree) {
                TypeElement enclosing = (TypeElement) trees.element(p);
                if (enclosing != null && elements.getAllMembers(enclosing).contains(member)) {
                    return false;
                }
            }
        }
        return true;
    }

    private boolean isGeneratedParameter(VariableElement v) {
        if (v.getKind() != ElementKind.PARAMETER || !(v.getEnclosingElement() instanceof ExecutableElement m)) {
            return false;
        }
        return elements.getOrigin(m) != Elements.Origin.EXPLICIT
               || elements.getOrigin(v) != Elements.Origin.EXPLICIT   // compact canonical constructor parameters
               || (m.getEnclosingElement() instanceof TypeElement t && t.getNestingKind() == NestingKind.ANONYMOUS
                   && m.getKind() == ElementKind.CONSTRUCTOR);
    }

    private static boolean isLocalish(VariableElement v) {
        return switch (v.getKind()) {
            case LOCAL_VARIABLE, PARAMETER, EXCEPTION_PARAMETER, RESOURCE_VARIABLE, BINDING_VARIABLE -> true;
            default -> false;
        };
    }

    /** doVisitReferenceElement: a local/parameter used inside a lambda or anonymous class that does not declare it. */
    private boolean capturedByAnonymousOrLambda(TreePath ref, VariableElement v) {
        TreePath decl = declarations.get(v);
        for (TreePath p = ref; p != null; p = p.getParentPath()) {
            Tree leaf = p.getLeaf();
            boolean anonymous = leaf instanceof ClassTree && trees.element(p) instanceof TypeElement t
                                && t.getNestingKind() == NestingKind.ANONYMOUS;
            if (leaf instanceof ClassTree && !anonymous) {
                return false;
            }
            if (anonymous || leaf instanceof LambdaExpressionTree) {
                if (decl == null || !isAncestor(p, decl)) {
                    return true;
                }
            }
        }
        return false;
    }

    private static boolean isAncestor(TreePath ancestor, TreePath of) {
        for (TreePath p = of; p != null; p = p.getParentPath()) {
            if (p.getLeaf() == ancestor.getLeaf()) {
                return true;
            }
        }
        return false;
    }

    /** ReassignedVariableInspection: non-final locals/parameters written more than once (parameters: written at all). */
    private void reassigned(VariableElement v, int s, int e) {
        if (v.getModifiers().contains(Modifier.FINAL)) {
            return;
        }
        int count = writes.getOrDefault(v, 0);
        boolean local = v.getKind() == ElementKind.LOCAL_VARIABLE || v.getKind() == ElementKind.RESOURCE_VARIABLE;
        boolean parameter = v.getKind() == ElementKind.PARAMETER || v.getKind() == ElementKind.EXCEPTION_PARAMETER
                            || v.getKind() == ElementKind.BINDING_VARIABLE;
        if ((local && count > 1) || (parameter && count > 0)) {
            add(s, e, "info", "reassigned", local ? "REASSIGNED_LOCAL_VARIABLE_ATTRIBUTES" : "REASSIGNED_PARAMETER_ATTRIBUTES");
        }
    }

    /** DeprecationInspection / MarkedForRemovalInspection on references. */
    private void deprecated(Element e, int s, int end) {
        if (e != null && elements.isDeprecated(e)) {
            Deprecated d = null;
            boolean forRemoval = e.getAnnotationMirrors().stream()
                    .anyMatch(a -> a.toString().contains("forRemoval=true"));
            add(s, end, "info", "deprecated API", forRemoval ? "MARKED_FOR_REMOVAL_ATTRIBUTES" : "DEPRECATED_ATTRIBUTES");
        }
    }

    // =====================================================================================
    // Javadoc references (visitDocTagValue / visitReferenceElement inside doc comments)
    // =====================================================================================

    private void javadoc() {
        new TreePathScanner<Void, Void>() {
            @Override
            public Void scan(Tree tree, Void unused) {
                if (tree != null && getCurrentPath() != null) {
                    TreePath path = new TreePath(getCurrentPath(), tree);
                    DocCommentTree doc = trees.api().getDocCommentTree(path);
                    if (doc != null && (tree instanceof ClassTree || tree instanceof MethodTree || tree instanceof VariableTree)) {
                        scanDoc(path, doc);
                    }
                }
                return super.scan(tree, unused);
            }
        }.scan(new TreePath(cu), null);
    }

    private void scanDoc(TreePath owner, DocCommentTree doc) {
        new DocTreePathScanner<Void, Void>() {
            @Override
            public Void visitReference(ReferenceTree node, Void unused) {
                DocTreePath p = getCurrentPath();
                int s = (int) trees.docPositions().getStartPosition(cu, doc, node);
                String sig = node.getSignature();
                Element target = trees.api().getElement(p);
                int hash = sig.indexOf('#');
                String typePart = hash < 0 ? sig : sig.substring(0, hash);
                if (!typePart.isEmpty()) {
                    Element type = target instanceof TypeElement ? target : target != null ? target.getEnclosingElement() : null;
                    if (type instanceof TypeElement t) {
                        add(s, s + typePart.length(), "info", "javadoc class reference", classKey(t, false));
                    }
                }
                if (hash >= 0 && target instanceof ExecutableElement m) {
                    String member = sig.substring(hash + 1).replaceAll("\\(.*", "");
                    int ms = s + hash + 1;
                    add(ms, ms + member.length(), "info", "javadoc method reference", methodKey(m, false, false, false));
                }
                return super.visitReference(node, unused);
            }

            @Override
            public Void visitParam(ParamTree node, Void unused) {
                if (!node.isTypeParameter()) {
                    Element target = trees.api().getElement(new DocTreePath(getCurrentPath(), node.getName()));
                    int s = (int) trees.docPositions().getStartPosition(cu, doc, node.getName());
                    if (target instanceof VariableElement v) {
                        add(s, s + node.getName().getName().length(), "info", "javadoc @param", variableKey(v, false, null));
                    }
                }
                return super.visitParam(node, unused);
            }
        }.scan(new DocTreePath(owner, doc), null);
    }

    // =====================================================================================
    // Output
    // =====================================================================================

    private String toJson() {
        javadoc();
        StringBuilder sb = new StringBuilder("{\"spans\":[\n");
        for (int i = 0; i < spans.size(); i++) {
            Span s = spans.get(i);
            sb.append(String.format("{\"start\":%d,\"end\":%d,\"layer\":\"%s\",\"keys\":[%s],\"why\":\"%s\"}%s%n",
                    s.start(), s.end(), s.layer(),
                    String.join(",", s.keys().stream().map(k -> "\"" + k + "\"").toList()),
                    s.why().replace("\\", "\\\\").replace("\"", "\\\""), i + 1 < spans.size() ? "," : ""));
        }
        return sb.append("]}\n").toString();
    }
}
