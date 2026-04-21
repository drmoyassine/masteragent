// craco.config.js
const path = require("path");
require("dotenv").config();

// Check if we're in development/preview mode (not production build)
// Craco sets NODE_ENV=development for start, NODE_ENV=production for build
const isDevServer = process.env.NODE_ENV !== "production";

// Environment variable overrides
const config = {
  enableHealthCheck: process.env.ENABLE_HEALTH_CHECK === "true",
  enableVisualEdits: isDevServer, // Only enable during dev server
};

// Conditionally load visual edits modules only in dev mode
let setupDevServer;
let babelMetadataPlugin;

if (config.enableVisualEdits) {
  setupDevServer = require("./plugins/visual-edits/dev-server-setup");
  babelMetadataPlugin = require("./plugins/visual-edits/babel-metadata-plugin");
}

// Conditionally load health check modules only if enabled
let WebpackHealthPlugin;
let setupHealthEndpoints;
let healthPluginInstance;

if (config.enableHealthCheck) {
  WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPluginInstance = new WebpackHealthPlugin();
}

const webpackConfig = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  },
  webpack: {
    alias: {
      // -----------------------------------------------------------------
      // @/ path alias
      '@': path.resolve(__dirname, 'src'),
      // -----------------------------------------------------------------
      // Force all prosemirror-* imports to resolve from a SINGLE top-level
      // copy. Without this, Webpack may bundle two separate class instances
      // (one from @milkdown/kit's transitive deps, one hoisted to the root),
      // which breaks `super()` in ProseMirror's class hierarchy at runtime.
      // -----------------------------------------------------------------
      'prosemirror-state':        path.resolve(__dirname, 'node_modules/prosemirror-state'),
      'prosemirror-view':         path.resolve(__dirname, 'node_modules/prosemirror-view'),
      'prosemirror-model':        path.resolve(__dirname, 'node_modules/prosemirror-model'),
      'prosemirror-transform':    path.resolve(__dirname, 'node_modules/prosemirror-transform'),
      'prosemirror-commands':     path.resolve(__dirname, 'node_modules/prosemirror-commands'),
      'prosemirror-keymap':       path.resolve(__dirname, 'node_modules/prosemirror-keymap'),
      'prosemirror-history':      path.resolve(__dirname, 'node_modules/prosemirror-history'),
      'prosemirror-inputrules':   path.resolve(__dirname, 'node_modules/prosemirror-inputrules'),
      'prosemirror-schema-list':  path.resolve(__dirname, 'node_modules/prosemirror-schema-list'),
      'prosemirror-dropcursor':   path.resolve(__dirname, 'node_modules/prosemirror-dropcursor'),
      'prosemirror-gapcursor':    path.resolve(__dirname, 'node_modules/prosemirror-gapcursor'),
      'prosemirror-markdown':     path.resolve(__dirname, 'node_modules/prosemirror-markdown'),
      'prosemirror-tables':       path.resolve(__dirname, 'node_modules/prosemirror-tables'),
    },
    configure: (webpackConfig) => {

      // -----------------------------------------------------------------
      // EXCLUDE @milkdown from CRA's node_modules babel-loader.
      //
      // CRA has a second babel-loader rule that processes ALL node_modules
      // through `babel-preset-react-app/dependencies`. That preset includes
      // `@babel/plugin-transform-class-properties` which transforms private
      // field initializers (#field = value) by moving them BEFORE super()
      // in the transpiled output. This breaks @milkdown/transformer's
      // ParserState class which uses `#marks = Mark.none` as a class field.
      //
      // Modern browsers natively support private fields, static blocks, etc.
      // so we simply exclude @milkdown from Babel entirely.
      // -----------------------------------------------------------------
      webpackConfig.module.rules.forEach((rule) => {
        if (!rule.oneOf) return;
        rule.oneOf.forEach((oneOfRule) => {
          if (
            oneOfRule.loader &&
            oneOfRule.loader.includes('babel-loader') &&
            oneOfRule.exclude
          ) {
            // CRA's default exclude for the node_modules babel-loader is:
            //   /@babel(?:\/|\\{1,2})runtime/
            // We extend it to ALSO exclude @milkdown packages.
            const origExclude = oneOfRule.exclude;
            oneOfRule.exclude = (filePath) => {
              // Normalize to forward slashes for cross-platform matching
              const normalized = filePath.replace(/\\/g, '/');
              if (normalized.includes('/@milkdown/') || normalized.includes('/milkdown/')) {
                return true; // exclude from babel = don't transpile
              }
              // Fall back to the original exclude behavior
              if (origExclude instanceof RegExp) return origExclude.test(filePath);
              if (typeof origExclude === 'function') return origExclude(filePath);
              return false;
            };
          }
        });
      });

      // Add ignored patterns to reduce watched directories
      webpackConfig.watchOptions = {
        ...webpackConfig.watchOptions,
        ignored: [
          '**/node_modules/**',
          '**/.git/**',
          '**/build/**',
          '**/dist/**',
          '**/coverage/**',
          '**/public/**',
        ],
      };

      // Add health check plugin to webpack if enabled
      if (config.enableHealthCheck && healthPluginInstance) {
        webpackConfig.plugins.push(healthPluginInstance);
      }
      return webpackConfig;
    },
  },
};

// Only add babel metadata plugin during dev server
if (config.enableVisualEdits && babelMetadataPlugin) {
  webpackConfig.babel = {
    plugins: [babelMetadataPlugin],
  };
}

webpackConfig.devServer = (devServerConfig) => {
  // Apply visual edits dev server setup only if enabled
  if (config.enableVisualEdits && setupDevServer) {
    devServerConfig = setupDevServer(devServerConfig);
  }

  // Add health check endpoints if enabled
  if (config.enableHealthCheck && setupHealthEndpoints && healthPluginInstance) {
    const originalSetupMiddlewares = devServerConfig.setupMiddlewares;

    devServerConfig.setupMiddlewares = (middlewares, devServer) => {
      // Call original setup if exists
      if (originalSetupMiddlewares) {
        middlewares = originalSetupMiddlewares(middlewares, devServer);
      }

      // Setup health endpoints
      setupHealthEndpoints(devServer, healthPluginInstance);

      return middlewares;
    };
  }

  return devServerConfig;
};

module.exports = webpackConfig;
