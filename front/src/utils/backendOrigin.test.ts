/**
 * Backend origin tests.
 *
 * Run with `npm test` (node --test). These lock in the deployment contract:
 * a production build must use its own origin (the reverse proxy forwards
 * `/api` and `/ws`), the dev server must reach uvicorn on port 8000, and the
 * build-time overrides must win.
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  resolveApiBaseUrl,
  resolveWsBaseUrl,
  type BackendOriginConfig,
} from "./backendOrigin.ts";

const PRODUCTION: BackendOriginConfig = {
  location: { protocol: "https:", hostname: "mench.example.com", host: "mench.example.com" },
  isDev: false,
};

const DEV: BackendOriginConfig = {
  location: { protocol: "http:", hostname: "localhost", host: "localhost:3000" },
  isDev: true,
};

test("production build uses the page origin for REST and sockets", () => {
  assert.equal(resolveApiBaseUrl(PRODUCTION), "");
  assert.equal(resolveWsBaseUrl(PRODUCTION), "wss://mench.example.com");
});

test("production keeps a non-default page port so a proxied port works", () => {
  const location = { protocol: "http:", hostname: "127.0.0.1", host: "127.0.0.1:8080" };
  const config = { ...PRODUCTION, location };

  assert.equal(resolveApiBaseUrl(config), "");
  assert.equal(resolveWsBaseUrl(config), "ws://127.0.0.1:8080");
});

test("dev build falls back to the local backend port", () => {
  assert.equal(resolveApiBaseUrl(DEV), "http://localhost:8000");
  assert.equal(resolveWsBaseUrl(DEV), "ws://localhost:8000");
});

test("dev fallback honours a custom backend port", () => {
  const config = { ...DEV, devBackendPort: "8010" };

  assert.equal(resolveApiBaseUrl(config), "http://localhost:8010");
  assert.equal(resolveWsBaseUrl(config), "ws://localhost:8010");
});

test("configured origins win and are normalised", () => {
  const config: BackendOriginConfig = {
    ...PRODUCTION,
    apiBaseUrl: " https://api.example.com/ ",
    wsBaseUrl: "wss://api.example.com/",
    isDev: true,
  };

  assert.equal(resolveApiBaseUrl(config), "https://api.example.com");
  assert.equal(resolveWsBaseUrl(config), "wss://api.example.com");
});

test("blank configuration is treated as absent", () => {
  const config: BackendOriginConfig = {
    ...DEV,
    apiBaseUrl: "   ",
    wsBaseUrl: "",
  };

  assert.equal(resolveApiBaseUrl(config), "http://localhost:8000");
  assert.equal(resolveWsBaseUrl(config), "ws://localhost:8000");
});
