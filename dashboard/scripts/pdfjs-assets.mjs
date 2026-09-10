import { readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const require = createRequire(import.meta.url);
const packagePath = require.resolve("pdfjs-dist/package.json");
const root = dirname(packagePath);
const { version } = JSON.parse(readFileSync(packagePath, "utf8"));

/** Serve the same versioned PDF resources in development and production. */
export function pdfjsAssets() {
  const files = new Map([["LICENSE", join(root, "LICENSE")]]);
  for (const directory of ["cmaps", "standard_fonts", "wasm", "iccs"]) {
    for (const entry of readdirSync(join(root, directory), {
      withFileTypes: true,
    })) {
      if (entry.isFile()) {
        files.set(
          `${directory}/${entry.name}`,
          join(root, directory, entry.name),
        );
      }
    }
  }
  return {
    name: "pdfjs-assets",
    configureServer(server) {
      server.middlewares.use(
        `${server.config.base}pdfjs/${version}/`,
        (req, res, next) => {
          const name = req.url?.split("?")[0].replace(/^\//, "");
          const file = files.get(name);
          if (!file) return next();
          res.setHeader(
            "Content-Type",
            name.endsWith(".wasm")
              ? "application/wasm"
              : /\.m?js$/.test(name)
              ? "text/javascript"
              : "application/octet-stream",
          );
          res.end(readFileSync(file));
        },
      );
    },
    generateBundle() {
      for (const [name, file] of files) {
        this.emitFile({
          type: "asset",
          fileName: `pdfjs/${version}/${name}`,
          source: readFileSync(file),
        });
      }
    },
  };
}
