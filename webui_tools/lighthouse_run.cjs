const fs = require('fs');
const path = require('path');
const https = require('https');
const { spawn } = require('child_process');

const PROFILE = {
  login: {
    route: '/giris',
    output: 'lighthouse-giris.html',
  },
  dashboard: {
    route: '/hastalar',
    output: 'lighthouse-dashboard.html',
  },
};

const candidates = [
  process.env.LIGHTHOUSE_ORIGIN || 'https://127.0.0.1:5443',
  'https://192.168.1.50:5443',
];

const mode = (process.argv[2] || 'all').toLowerCase();
const targets = mode === 'all'
  ? ['login', 'dashboard']
  : [mode];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function canReach(url) {
  return new Promise((resolve) => {
    const req = https.request(url, {
        method: 'HEAD',
        headers: { 'User-Agent': 'lighthouse-probe/1.0' },
        timeout: 4000,
        rejectUnauthorized: false,
      }, () => {
        resolve(true);
      });

    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });

    req.end();
  });
}

async function resolveTarget(route) {
  for (const origin of candidates) {
    const full = `${origin}${route}`;
    const ok = await canReach(full);
    if (ok) return full;
  }
  return null;
}

function createTempDir(prefix) {
  const base = path.join(process.cwd(), '.lh-run-tmp');
  const dir = path.join(base, `${prefix}-${Date.now()}-${process.pid}`);
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function removeSilently(target) {
  try {
    if (fs.existsSync(target)) {
      fs.rmSync(target, { recursive: true, force: true, maxRetries: 2, retryDelay: 200 });
    }
  } catch (e) {
    // Best effort cleanup only.
  }
}

async function runLighthouse(url, output) {
  const baseTemp = createTempDir('lh');
  const userDir = createTempDir('lh-user');

  const chromeFlags = [
    '--headless',
    '--ignore-certificate-errors',
    '--allow-insecure-localhost',
    '--no-sandbox',
    '--disable-dev-shm-usage',
    `--user-data-dir=${userDir}`,
  ].join(' ');

  const args = [
    'lighthouse',
    url,
    '--output', 'html',
    '--output-path', output,
    '--chrome-flags', chromeFlags,
    '--disable-storage-reset',
    '--skip-audits=bf-cache',
    '--no-enable-error-reporting',
  ];

  try {
    await new Promise((resolve, reject) => {
      const cliCommand = path.join(process.cwd(), 'node_modules', 'lighthouse', 'cli', 'index.js');
      const outPath = path.join(process.cwd(), output);
      let stdout = '';
      let stderr = '';
      let rawStdout = '';
      let rawStderr = '';
      const child = spawn(process.execPath, [cliCommand, ...args], {
        cwd: process.cwd(),
        stdio: ['ignore', 'pipe', 'pipe'],
        env: {
          ...process.env,
          TMP: baseTemp,
          TEMP: baseTemp,
          TMPDIR: baseTemp,
        },
      });

      child.stdout.on('data', (chunk) => {
        const text = chunk.toString();
        rawStdout += text;
        if (!text.includes('Error: EPERM, Permission denied')) {
          stdout += text;
          process.stdout.write(text);
        }
      });
      child.stderr.on('data', (chunk) => {
        const text = chunk.toString();
        rawStderr += text;
        if (!text.includes('Error: EPERM, Permission denied') && !text.includes("code: 'EPERM'")) {
          stderr += text;
          process.stderr.write(text);
        }
      });

      child.on('error', reject);
      child.on('exit', (code) => {
        const logs = `${rawStdout}${rawStderr}`;
        const hadEpError = logs.includes('Runtime error encountered: EPERM') || logs.includes('Permission denied');
        const hasOutput = fs.existsSync(outPath);
        if (code === 0 || (code === 1 && hadEpError && hasOutput)) {
          if (hadEpError) {
            console.log(`Lighthouse completed with EPERM warning. Report file: ${output}`);
          }
          resolve();
        } else {
          reject(new Error(`lighthouse failed with exit code ${code}`));
        }
      });
    });
  } finally {
    removeSilently(baseTemp);
    removeSilently(userDir);
  }
}

async function main() {
  const targetModes = targets.filter((item) => Object.hasOwn(PROFILE, item));
  if (!targetModes.length) {
    console.error(`Unsupported mode: ${mode}. Use one of: all, login, dashboard`);
    process.exit(1);
  }

  for (const key of targetModes) {
    const profile = PROFILE[key];
    const target = await resolveTarget(profile.route);

    if (!target) {
      console.error(`Could not reach ${profile.route} on any candidate origin.`);
      process.exit(1);
    }

    console.log(`Running Lighthouse for ${target} -> ${profile.output}`);
    await runLighthouse(target, profile.output);
    await sleep(300);
  }

  console.log('Lighthouse runs completed.');
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
