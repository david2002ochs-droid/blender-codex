// Run the current compiled UI contracts from a fresh checkout.
const {spawnSync} = require('node:child_process');
const {createRequire} = require('node:module');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const resolveBrowserDependency = createRequire(path.join(__dirname, 'browser/package.json'));
const env = {...process.env};
env.PLAYWRIGHT_MODULE ||= resolveBrowserDependency.resolve('playwright');
function run(command, args) {
  const result = spawnSync(command, args, {cwd: root, env, stdio: 'inherit'});
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status || 1);
}
run(env.PYTHON || 'python', ['tests/test_reasoning.py', '--export', '.runtime/thinking-replay-states.json']);
for (const name of ['deepblick_frontend', 'image_annotation', 'thinking_frontend', 'blender_hero']) {
  run(process.execPath, ['tests/test_' + name + '.cjs']);
}
