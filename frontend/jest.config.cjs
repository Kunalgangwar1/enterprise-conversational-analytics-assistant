module.exports = {
  testEnvironment: "jsdom",
  transform: { "^.+\\.(ts|tsx)$": "babel-jest" },
  setupFilesAfterEnv: ["<rootDir>/src/setupTests.ts"],
  moduleFileExtensions: ["ts", "tsx", "js"],
  clearMocks: true,
};
