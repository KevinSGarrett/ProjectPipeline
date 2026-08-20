import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const desktopRoot = path.resolve(frontendRoot, "../desktop_shell");
const configPath = path.join(desktopRoot, "src-tauri", "tauri.conf.json");
const cliPath = path.join(frontendRoot, "node_modules", "@tauri-apps", "cli", "tauri.js");

if (!fs.existsSync(configPath)) {
  process.stderr.write(`Tauri project config missing: ${configPath}\n`);
  process.exit(1);
}
if (!fs.existsSync(cliPath)) {
  process.stderr.write(`Tauri CLI missing: ${cliPath}\n`);
  process.exit(1);
}

const env = {
  ...process.env,
  TAURI_FRONTEND_PATH: frontendRoot,
  TAURI_APP_PATH: path.join(desktopRoot, "src-tauri"),
};

const result = spawnSync(process.execPath, [cliPath, ...process.argv.slice(2)], {
  cwd: desktopRoot,
  env,
  stdio: "inherit",
  windowsHide: true,
});

process.exit(result.status ?? 1);
