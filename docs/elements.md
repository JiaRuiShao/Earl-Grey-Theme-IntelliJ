| Java element | Examples | Identical | VS Code | IntelliJ key |
|---|---|---|---|---|
| Class | `IOException`, `StringReader`, `ArrayList` | ✅ 82/82 | `#605A52 italic` | `CLASS_NAME_ATTRIBUTES` |
| Abstract class | `Animal` | ✅ 4/4 | `#605A52 italic` | `ABSTRACT_CLASS_NAME_ATTRIBUTES` |
| Interface | `List`, `Map`, `BiFunction` | ✅ 30/30 | `#605A52 italic` | `INTERFACE_NAME_ATTRIBUTES` |
| Interface (in Javadoc) | `Shape` | ✅ 1/1 | `#605A52 italic` | `INTERFACE_NAME_ATTRIBUTES` |
| Enum | `ElementType`, `RetentionPolicy`, `Planet` | ✅ 7/7 | `#605A52 italic` | `ENUM_NAME_ATTRIBUTES` |
| Enum (in Javadoc) | `Planet` | ✅ 1/1 | `#605A52 italic` | `ENUM_NAME_ATTRIBUTES` |
| Record | `Point`, `Num`, `Add` | ✅ 10/10 | `#605A52 italic` | `RECORD_NAME_ATTRIBUTES` |
| Annotation | `Retention`, `Target`, `@Marker` | ⚠️ 3/13 | `#7F7A73` | `ANNOTATION_NAME_ATTRIBUTES` |
| Anonymous class (base type) | `Runnable` | ✅ 1/1 | `#605A52 italic` | `ANONYMOUS_CLASS_NAME_ATTRIBUTES` |
| Type parameter | `T`, `R` | ✅ 12/12 | `#886A44 italic` | `TYPE_PARAMETER_NAME_ATTRIBUTES` |
| Package name | `com.`, `earlgrey.`, `demo` | ❌ 0/45 | `#886A44` | `CLASS_NAME_ATTRIBUTES` |
| Constructor declaration | `Showcase`, `Point`, `Planet` | ✅ 5/5 | `#605A52 italic` | `CONSTRUCTOR_DECLARATION_ATTRIBUTES` |
| Constructor call (new) | `ArrayList`, `StringBuilder`, `StringReader` | ✅ 10/10 | `#605A52 italic` | `CONSTRUCTOR_CALL_ATTRIBUTES` |
| Method declaration | `get`, `add`, `transform` | ✅ 29/29 | `#605A52 italic` | `METHOD_DECLARATION_ATTRIBUTES` |
| Method call | `isEmpty`, `append`, `println` | ✅ 25/25 | `#605A52 italic` | `METHOD_CALL_ATTRIBUTES` |
| Static method call | `max`, `emptyList`, `of` | ✅ 7/7 | `#605A52 italic` | `STATIC_METHOD_ATTRIBUTES` |
| Static method, statically imported | `max` | ✅ 1/1 | `#605A52 italic` | `STATIC_METHOD_IMPORTED_ATTRIBUTES` |
| Abstract / interface method call | `add`, `apply`, `size` | ✅ 14/14 | `#605A52 italic` | `ABSTRACT_METHOD_ATTRIBUTES` |
| Abstract / interface method call (in Javadoc) | `area` | ✅ 1/1 | `#605A52 italic` | `ABSTRACT_METHOD_ATTRIBUTES` |
| Inherited method call | `name`, `speak` | ✅ 2/2 | `#605A52 italic` | `INHERITED_METHOD_ATTRIBUTES` |
| Annotation attribute | `value`, `priority` | ✅ 2/2 | `#605A52 italic` | `ANNOTATION_ATTRIBUTE_NAME_ATTRIBUTES` |
| Instance field | `size`, `running`, `timestamp` | ✅ 19/19 | `#556995` | `INSTANCE_FIELD_ATTRIBUTES` |
| Instance final field | `items`, `length`, `mass` | ✅ 9/9 | `#556995` | `INSTANCE_FINAL_FIELD_ATTRIBUTES` |
| Static field | `hits` | ✅ 4/4 | `#556995` | `STATIC_FIELD_ATTRIBUTES` |
| Static field, statically imported | `hits` | ✅ 1/1 | `#556995` | `STATIC_FIELD_IMPORTED_ATTRIBUTES` |
| Static final field (constant) | `PI`, `GREETING`, `MAX_SIZE` | ✅ 13/13 | `#556995` | `STATIC_FINAL_FIELD_ATTRIBUTES` |
| Constant, statically imported | `PI` | ✅ 1/1 | `#556995` | `STATIC_FINAL_FIELD_IMPORTED_ATTRIBUTES` |
| Enum constant | `RUNTIME`, `TYPE`, `METHOD` | ❌ 0/6 | `#605A52 italic` | `STATIC_FINAL_FIELD_ATTRIBUTES` |
| Record component | `value`, `left`, `right` | ✅ 11/11 | `#556995` | `RECORD_COMPONENT_ATTRIBUTES` |
| Local variable | `result`, `item`, `total` | ✅ 59/59 | `#556995` | `LOCAL_VARIABLE_ATTRIBUTES` |
| Parameter (method, catch, pattern) | `initialSize`, `item`, `mapper` | ✅ 57/57 | `#556995` | `PARAMETER_ATTRIBUTES` |
| Parameter (method, catch, pattern) (in Javadoc) | `initialSize` | ✅ 1/1 | `#556995 italic` | `PARAMETER_ATTRIBUTES` |
| Lambda parameter | `n`, `s`, `times` | ✅ 7/7 | `#556995` | `LAMBDA_PARAMETER_ATTRIBUTES` |
| Variable captured by lambda / anonymous class | `builder`, `area` | ✅ 2/2 | `#556995` | `IMPLICIT_ANONYMOUS_CLASS_PARAMETER_ATTRIBUTES` |
| Keyword / modifier | `package`, `import`, `static` | ✅ 139/139 | `#83577D` | `JAVA_KEYWORD` |
| Primitive type | `int`, `boolean`, `long` | ✅ 43/43 | `#83577D` | `JAVA_KEYWORD` |
| Keyword: this | `this` | ✅ 6/6 | `#83577D` | `JAVA_KEYWORD` |
| Keyword: super | `super` | ⚠️ 1/3 | `#477A7B` | `JAVA_KEYWORD` |
| Keyword: instanceof | `instanceof` | ❌ 0/5 | `#605A52` | `JAVA_KEYWORD` |
| Literal keyword (true, false, null) | `true`, `null`, `false` | ❌ 0/4 | `#477A7B` | `JAVA_KEYWORD` |
| Contextual keyword (record, sealed, permits, yield) | `yield`, `sealed`, `permits` | ✅ 8/8 | `#83577D` | `JAVA_KEYWORD` |
| Contextual keyword (var) | `var` | ❌ 0/1 | `#605A52 italic` | `JAVA_KEYWORD` |
| Contextual keyword (when) | `when` | ❌ 0/1 | `#605A52` | `JAVA_KEYWORD` |
| String / char / text block | `"showcase"`, `"Hello, \"tea\"\n"`, `"unchecked"` | ❌ 0/27 | `#7F7A73` | `JAVA_STRING` |
| String escape | `\"`, `\n`, `\t` | ⚠️ 4/5 | `#477A7B` | `JAVA_STRING + JAVA_VALID_STRING_ESCAPE` |
| Number | `2`, `0`, `0x7F_FF` | ✅ 39/39 | `#477A7B` | `JAVA_NUMBER` |
| Operator | `=`, `>>>`, `++` | ⚠️ 105/117 | `#605A52` | `JAVA_OPERATION_SIGN` |
| Generic angle bracket | `<`, `>>`, `>` | ❌ 0/43 | `#7F7A73` | `JAVA_OPERATION_SIGN` |
| Comma | `,` | ✅ 25/25 | `#7F7A73` | `JAVA_COMMA` |
| Dot | `.` | ✅ 61/61 | `#7F7A73` | `JAVA_DOT` |
| Semicolon | `;` | ✅ 115/115 | `#7F7A73` | `JAVA_SEMICOLON` |
| Brackets ( ) [ ] { } | `(`, `)`, `{` | ❌ 0/378 | `#6B9494` | `JAVA_PARENTH` |
| Line comment | `// ----- fields -----`, `// static field`, `// static final field (constant)` | ✅ 20/20 | `#9E9A95 italic` | `JAVA_LINE_COMMENT` |
| Javadoc tag | `@link`, `@code`, `@param` | ✅ 7/7 | `#83577D italic` | `JAVA_DOC_COMMENT + JAVA_DOC_TAG` |
| Javadoc HTML | `<p>` | ✅ 1/1 | `#9E9A95 italic` | `JAVA_DOC_COMMENT + JAVA_DOC_MARKUP` |
| TODO comment | `TODO: steep for three minutes` | ✅ 1/1 | `#9E9A95 italic wave` | `TODO_DEFAULT_ATTRIBUTES` |
