/**
 * CSS contract tests.
 *
 * Tailwind v3 silently drops unknown utilities, so a typo such as `z-45` or a
 * class that needs a plugin (`scrollbar-thin`) just does nothing. These tests
 * keep the three regressions from the frontend-quality issue from coming back:
 * an undefined animation, undefined utilities, and a document that locks
 * scrolling and text selection.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const FRONT_ROOT = new URL("../../", import.meta.url).pathname;
const SOURCE_ROOT = join(FRONT_ROOT, "src");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    if (!/\.tsx?$/.test(entry.name) || entry.name.endsWith(".test.ts")) return [];
    return [path];
  });
}

function allSource(): string {
  return sourceFiles(SOURCE_ROOT)
    .map((path) => readFileSync(path, "utf8"))
    .join("\n");
}

test("the fade-in animation used by the overlays is defined", () => {
  const config = readFileSync(join(FRONT_ROOT, "tailwind.config.js"), "utf8");

  assert.match(config, /'fade-in':/);
  assert.match(allSource(), /animate-fade-in/);
});

test("every themed colour has a CSS variable behind it", () => {
  const config = readFileSync(join(FRONT_ROOT, "tailwind.config.js"), "utf8");
  const css = readFileSync(join(SOURCE_ROOT, "index.css"), "utf8");
  const used = [...config.matchAll(/var\((--[a-z-]+)\)/g)].map(
    (match) => match[1],
  );

  assert.ok(used.length >= 10, "tailwind.config.js should map the palette");
  for (const name of used) {
    assert.match(
      css,
      new RegExp(`\\s${name}\\s*:`),
      `${name} is mapped in tailwind.config.js but never defined in index.css`,
    );
  }
});

test("no undefined Tailwind utilities are used", () => {
  const source = allSource();

  assert.ok(!/z-45\b/.test(source), "z-45 is not in the default scale; use z-[45]");
  assert.ok(
    !/\bscrollbar-thin\b/.test(source),
    "scrollbar-thin needs the tailwind-scrollbar plugin",
  );
});

test("the document does not lock scrolling or text selection", () => {
  const html = readFileSync(join(FRONT_ROOT, "index.html"), "utf8");
  const body = html.match(/<body[^>]*class="([^"]*)"/)?.[1] ?? "";

  assert.ok(!body.includes("select-none"));
  assert.ok(!body.includes("overflow-hidden"));
});
