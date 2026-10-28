import { existsSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);

// Remotion downloads its own Chrome Headless Shell on first render. Where that
// download is blocked (sandboxed or offline machines), reuse one already on disk:
// REMOTION_BROWSER_EXECUTABLE first, then Playwright's and HyperFrames' copies.
const findHeadlessShell = (): string | null => {
  const fromEnv = process.env.REMOTION_BROWSER_EXECUTABLE;
  if (fromEnv && existsSync(fromEnv)) return fromEnv;

  const roots = [
    process.env.PLAYWRIGHT_BROWSERS_PATH ?? "/opt/pw-browsers",
    join(homedir(), ".cache/ms-playwright"),
    join(homedir(), ".cache/hyperframes/chrome/chrome-headless-shell"),
  ];
  for (const root of roots) {
    if (!existsSync(root)) continue;
    for (const dir of readdirSync(root).sort().reverse()) {
      if (!dir.includes("headless") && !dir.startsWith("linux-")) continue;
      const candidate = join(root, dir, "chrome-headless-shell-linux64", "chrome-headless-shell");
      if (existsSync(candidate)) return candidate;
    }
  }
  return null;
};

const headlessShell = findHeadlessShell();
if (headlessShell) Config.setBrowserExecutable(headlessShell);
