/**
 * @fileoverview Central configuration constants for plan-audit-map
 *
 * Overlay note (plan-audit-map-desk): this file replaces src/utils/config.ts
 * from the upstream repo with one difference — PLAN_AUDIT_MAP_HOME /
 * PLAN_AUDIT_MAP_CONFIG_DIR environment overrides are honoured, matching the
 * Python desk stack (mtd_shared.py).  Without this, the prompts/values
 * files and the memory database could live in two different "config dirs".
 *
 * This file defines:
 * 1. Filesystem paths for components that need filesystem access (prompts)
 * 2. Default application constants
 *
 * Note: The main configuration system is in-memory only and doesn't use
 * filesystem persistence for configuration values.  The filesystem paths
 * defined here are only used for prompt-related functionality.
 */

import os from 'os';
import path from 'path';
import fs from 'fs';

// Filesystem paths for prompt-related functionality
export const USER_HOME = os.homedir();
export const DEFAULT_CONFIG_DIR = path.join(USER_HOME, '.plan-audit-map');
export const LEGACY_CONFIG_DIR = path.join(USER_HOME, '.code-reasoning');

// Environment overrides (honoured by the Python desk stack as well).
function envConfigDir(): string | null {
  const raw = process.env.PLAN_AUDIT_MAP_HOME || process.env.PLAN_AUDIT_MAP_CONFIG_DIR || '';
  if (raw.trim()) {
    return path.resolve(raw.trim());
  }
  return null;
}

function resolveConfigDir(): string {
  const env = envConfigDir();
  if (env) {
    return env;
  }

  if (fs.existsSync(DEFAULT_CONFIG_DIR)) {
    return DEFAULT_CONFIG_DIR;
  }

  if (fs.existsSync(LEGACY_CONFIG_DIR)) {
    return LEGACY_CONFIG_DIR;
  }

  return DEFAULT_CONFIG_DIR;
}

export const CONFIG_DIR = resolveConfigDir();
export const PROMPT_VALUES_FILE = path.join(CONFIG_DIR, 'prompt_values.json');
export const CUSTOM_PROMPTS_DIR = path.join(CONFIG_DIR, 'prompts');

// Application defaults (used by the in-memory configuration)
export const MAX_THOUGHT_LENGTH = 20000;
export const MAX_THOUGHTS = 20;
// Maximum number of recent thoughts passed as context to bias detection.
// Keeping this small avoids cloning large strings on every processThought call.
export const MAX_PREVIOUS_THOUGHTS_CONTEXT = 5;
