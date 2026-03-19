/**
 * Back-compat barrel: prefer importing from ./backendApi.js, ./http.js, ./config.js
 * so tree-shaking and TS migration stay obvious.
 */
export {
  checkHealth,
  createSession,
  sendMessage,
  getPlan,
  patchAction,
  approveAll,
  executePlan,
} from "./backendApi.js";
