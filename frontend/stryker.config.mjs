/** @type {import('@stryker-mutator/api/core').PartialStrykerOptions} */
export default {
  testRunner: "vitest",
  coverageAnalysis: "perTest",
  mutate: [
    "src/**/*.ts",
    "src/**/*.tsx",
    "!src/**/*.test.ts",
    "!src/**/*.test.tsx",
    "!src/main.tsx",
    "!src/test/**",
  ],
  thresholds: { high: 80, low: 60, break: null },
  reporters: ["clear-text", "html"],
  htmlReporter: { fileName: "reports/mutation/index.html" },
};
