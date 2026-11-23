import ts from "typescript";

/** Resolve imported locale bundles from the actual TypeScript export structure. */
export function readLocaleTree(source, readBundle, filename = "locale/index.ts") {
  const file = ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  if (file.parseDiagnostics.length) {
    throw new SyntaxError(ts.flattenDiagnosticMessageText(file.parseDiagnostics[0].messageText, "\n"));
  }
  const imports = new Map();
  let exported;
  for (const statement of file.statements) {
    if (
      ts.isImportDeclaration(statement) &&
      statement.importClause?.name &&
      ts.isStringLiteral(statement.moduleSpecifier)
    ) {
      imports.set(statement.importClause.name.text, statement.moduleSpecifier.text);
    } else if (ts.isExportAssignment(statement) && !statement.isExportEquals) {
      exported = statement.expression;
    }
  }

  const resolve = (expression) => {
    if (
      ts.isParenthesizedExpression(expression) ||
      ts.isAsExpression(expression) ||
      ts.isSatisfiesExpression(expression)
    ) {
      return resolve(expression.expression);
    }
    if (ts.isIdentifier(expression)) {
      const path = imports.get(expression.text);
      if (!path) throw new Error(`unresolved locale import ${expression.text} in ${filename}`);
      return readBundle(path);
    }
    if (!ts.isObjectLiteralExpression(expression)) {
      throw new Error(`unsupported locale value in ${filename}: ${expression.getText(file)}`);
    }
    return Object.fromEntries(
      expression.properties.map((property) => {
        if (ts.isShorthandPropertyAssignment(property)) return [property.name.text, resolve(property.name)];
        if (
          !ts.isPropertyAssignment(property) ||
          !(ts.isIdentifier(property.name) || ts.isStringLiteral(property.name) || ts.isNumericLiteral(property.name))
        ) {
          throw new Error(`unsupported locale property in ${filename}: ${property.getText(file)}`);
        }
        return [property.name.text, resolve(property.initializer)];
      }),
    );
  };

  if (!exported) throw new Error(`missing default locale export in ${filename}`);
  return resolve(exported);
}
