import { spawnSync } from "node:child_process";
import { readFileSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packageDirectory = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(packageDirectory, "..", "..");
const exporter = resolve(repositoryRoot, "backend", "scripts", "export_openapi.py");
const specification = resolve(packageDirectory, "openapi.json");
const generatedTypes = resolve(packageDirectory, "src", "generated", "schema.d.ts");
const temporaryTypes = resolve(packageDirectory, ".schema-check.d.ts");
const generatorPackageDirectory = resolve(repositoryRoot, "node_modules", "openapi-typescript");
const generatorPackage = JSON.parse(
  readFileSync(resolve(generatorPackageDirectory, "package.json"), "utf8"),
);
const generatorEntry = typeof generatorPackage.bin === "string"
  ? generatorPackage.bin
  : generatorPackage.bin["openapi-typescript"];
const check = process.argv.includes("--check");

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: repositoryRoot,
    stdio: "inherit",
    ...options,
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`${command} exited with status ${result.status ?? "unknown"}.`);
  }
}

const python = process.platform === "win32" ? "python" : "python3";
run(python, [exporter, ...(check ? ["--check"] : [])]);

const outputTypes = check ? temporaryTypes : generatedTypes;
try {
  run(
    process.execPath,
    [resolve(generatorPackageDirectory, generatorEntry), specification, "-o", outputTypes],
    { cwd: packageDirectory },
  );
  if (check) {
    const current = readFileSync(generatedTypes, "utf8");
    const fresh = readFileSync(temporaryTypes, "utf8");
    if (current !== fresh) {
      console.error("Generated API types are stale. Run npm run api:generate.");
      process.exitCode = 1;
    }
  }
} finally {
  if (check) {
    rmSync(temporaryTypes, { force: true });
  }
}
