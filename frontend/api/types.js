/**
 * JSDoc shapes aligned with FastAPI + docs/FE_BE_INTEGRATION.md
 * When you migrate to TypeScript, replace this file with types.ts / generated OpenAPI types.
 *
 * @typedef {Object} HealthSnapshot
 * @property {string} status
 * @property {string} [db]
 * @property {string} [model_provider]
 * @property {string} [model_name]
 * @property {string} [model_status]
 * @property {string} [ollama]
 */

/**
 * @typedef {Object} CreateSessionBody
 * @property {string} user_id
 * @property {string} [mode]
 */

/**
 * @typedef {Object} SendMessageBody
 * @property {string} content
 */

export {};
