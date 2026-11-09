import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import crypto from 'node:crypto';

const here = path.dirname(fileURLToPath(import.meta.url));
const vendor = path.join(here, 'vendor/deepblick');
const root = path.dirname(here);
const argument = process.argv.indexOf('--dependency-root');
const dependencyRoot = argument >= 0 ? path.resolve(process.argv[argument + 1]) : process.env.DEEPBLICK_DEPENDENCY_ROOT;
const ownRequire = createRequire(path.join(here, 'package.json'));
const fallbackRequire = dependencyRoot ? createRequire(path.join(dependencyRoot, 'node_modules/vite/package.json')) : null;
let esbuild;
try { esbuild = ownRequire('esbuild'); } catch (error) {
  if (!fallbackRequire) throw new Error('Install frontend dependencies, or provide --dependency-root with prepared upstream node_modules.', {cause: error});
  esbuild = fallbackRequire('esbuild');
}
const provenance = JSON.parse(fs.readFileSync(path.join(vendor, 'SOURCE.json'), 'utf8'));
for (const file of provenance.files) {
  const data = fs.readFileSync(path.join(vendor, file.path));
  if (crypto.createHash('sha256').update(data).digest('hex') !== file.sha256) throw new Error('Modified pinned source: ' + file.path);
}
const aliases = new Map();
for (const entry of provenance.files.filter(file => file.path.endsWith('/package.json'))) {
  const directory = path.dirname(path.join(vendor, entry.path));
  const manifest = JSON.parse(fs.readFileSync(path.join(directory, 'package.json'), 'utf8'));
  aliases.set(manifest.name, directory);
}
const used = new Map();
const direct = new Map();
const packageDirectories = new Map();
function packageRecord(resolved) {
  let dir = path.dirname(resolved);
  while (dir !== path.dirname(dir)) {
    const manifestPath = path.join(dir, 'package.json');
    if (fs.existsSync(manifestPath)) {
      const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
      if (manifest.name && manifest.version) {
        used.set(manifest.name, manifest.version);
        packageDirectories.set(manifest.name, dir);
        return {directory: dir, manifest};
      }
    }
    dir = path.dirname(dir);
  }
}
const dependencyPlugin = {
  name: 'pinned-deepblick-view-imports',
  setup(build) {
    build.onResolve({filter: /^\./}, args => {
      const base = path.resolve(args.resolveDir, args.path);
      for (const candidate of [base, ...['.tsx', '.ts', '.jsx', '.js', '.mjs', '.json', '/index.ts', '/index.js'].map(ext => base + ext)]) {
        if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return {path: candidate};
      }
    });
    build.onResolve({filter: /^@deepseek-ai\//}, args => {
      const base = [...aliases.keys()].find(name => args.path === name || args.path.startsWith(name + '/'));
      if (!base) throw new Error('Unvendored production dependency: ' + args.path);
      const dir = aliases.get(base); const sub = args.path.slice(base.length);
      const candidates = sub === '/client' ? ['src/client/index.ts', 'src/client.ts'] : sub ? [sub.slice(1), 'src' + sub + '.ts', 'src' + sub + '/index.ts'] : ['src/index.ts'];
      for (const candidate of candidates) if (fs.existsSync(path.join(dir, candidate))) return {path: path.join(dir, candidate)};
      throw new Error('No source export for ' + args.path);
    });
    build.onResolve({filter: /^[^./]|^@/}, args => {
      if (/^(?:data:|https?:|node:)/.test(args.path)) return;
      if (args.kind === 'url-token') {
        const asset = path.resolve(args.resolveDir, args.path);
        if (fs.existsSync(asset)) return {path: asset};
      }
      const resolverOptions = [];
      if (dependencyRoot && /^(react(?:-dom)?(?:\/|$)|lexical$)/.test(args.path)) resolverOptions.push(createRequire(path.join(dependencyRoot, 'packages/client/ui-conversation/package.json')));
      if (args.importer && !args.importer.startsWith(vendor)) resolverOptions.push(createRequire(args.importer));
      // All production source is vendored. A prepared source checkout is used
      // only as a read-only npm dependency cache, never as application code.
      if (dependencyRoot && args.importer.startsWith(vendor)) {
        const relative = path.relative(vendor, args.importer).split(path.sep);
        resolverOptions.push(createRequire(path.join(dependencyRoot, ...relative.slice(0, 3), 'package.json')));
      }
      resolverOptions.push(ownRequire);
      if (fallbackRequire) resolverOptions.push(fallbackRequire);
      for (const resolve of resolverOptions) {
        try {
          let resolved = resolve.resolve(args.path);
          const record = packageRecord(resolved);
          if (record && (args.importer.startsWith(vendor) || args.importer.startsWith(path.join(here, 'src')))) direct.set(record.manifest.name, record.manifest.version);
          // createRequire locates installed packages, but browser ESM imports
          // must retain their import condition to permit real tree-shaking.
          if (record && args.path === 'simple-icons' && args.kind !== 'require-call') {
            const subpath = args.path === record.manifest.name ? '.' : './' + args.path.slice(record.manifest.name.length + 1);
            const exp = record.manifest.exports?.[subpath];
            let imported = exp?.import || exp?.module;
            while (imported && typeof imported === 'object') imported = imported.default || imported.browser;
            if (typeof imported === 'string' && fs.existsSync(path.join(record.directory, imported))) resolved = path.join(record.directory, imported);
          }
          return {path: resolved, ...(record?.manifest.sideEffects === false ? {sideEffects: false} : {})};
        } catch (_) { /* Try next installed dependency scope. */ }
      }
      throw new Error('Missing frontend dependency: ' + args.path + ' from ' + args.importer);
    });
  },
};
const output = path.join(root, 'blender_codex/web');
await esbuild.build({
  entryPoints: [path.join(here, 'src/main.tsx')], outfile: path.join(output, 'app.js'),
  bundle: true, minifyWhitespace: true, minifySyntax: true, minifyIdentifiers: false, sourcemap: false, format: 'iife', platform: 'browser', target: ['chrome110'],
  tsconfigRaw: {compilerOptions: {jsx: 'react-jsx', target: 'ES2022'}},
  jsx: 'automatic', define: {'process.env.NODE_ENV': '"production"', 'process.env.DSH_CLIENT_TITLE': '"Deepblick"', 'process.env.DSH_CLIENT_VERSION': 'undefined', 'process.env.DSH_CLIENT_COMMIT_HASH': 'undefined', 'process.env.DSH_CLIENT_GIT_DIRTY': '"false"'},
  loader: {'.module.css': 'local-css', '.woff2': 'dataurl', '.woff': 'dataurl', '.ttf': 'dataurl', '.png': 'dataurl', '.svg': 'dataurl', '.wasm': 'binary'},
  plugins: [dependencyPlugin], legalComments: 'inline', metafile: true,
}).then(result => {
  fs.writeFileSync(path.join(here, 'build-meta.json'), JSON.stringify(result.metafile, null, 2));
});
fs.renameSync(path.join(output, 'app.css'), path.join(output, 'styles.css'));
fs.copyFileSync(path.join(here, 'index.html'), path.join(output, 'index.html'));
fs.copyFileSync(path.join(vendor, 'LICENSE'), path.join(output, 'DEEPBLICK-LICENSE.txt'));
const notices = [fs.readFileSync(path.join(vendor, 'LICENSE'), 'utf8')];
for (const entry of provenance.files.filter(file => /(?:LICENSE|OFL|NOTICE|COPYING)/i.test(path.basename(file.path)) && file.path !== 'LICENSE')) notices.push(`\n--- ${entry.path} ---\n` + fs.readFileSync(path.join(vendor, entry.path), 'utf8'));
for (const [name, directory] of [...packageDirectories].sort()) {
  for (const filename of fs.readdirSync(directory).filter(name => /^(?:license|notice|copying)(?:[.\-_]|$)/i.test(name))) {
    const file = path.join(directory, filename);
    if (fs.statSync(file).isFile()) notices.push(`\n--- ${name}/${filename} ---\n` + fs.readFileSync(file, 'utf8'));
  }
}
fs.writeFileSync(path.join(output, 'THIRD-PARTY-NOTICES.txt'), notices.join('\n'));
const buildInfo = {source: provenance.repository, commit: provenance.commit, entry: 'frontend/src/main.tsx', directDependencies: Object.fromEntries([...direct].sort()), dependencies: Object.fromEntries([...used].sort())};
fs.writeFileSync(path.join(here, 'BUILD.json'), JSON.stringify(buildInfo, null, 2));
console.log('Built real Deepblick views at ' + provenance.commit + ' into blender_codex/web (no Harness runtime).');
