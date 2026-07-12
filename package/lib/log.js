// Thin console helpers. Kept separate so handlers don't import clack directly
// and tests can stub these. Symbols mirror @clack/prompts' visual language.

const C = {
  reset: '\x1b[0m',
  dim: '\x1b[2m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  red: '\x1b[31m',
  cyan: '\x1b[36m',
  bold: '\x1b[1m',
};

function paint(color, s) {
  return process.env.NO_COLOR ? s : `${color}${s}${C.reset}`;
}

export const log = {
  step(msg) {
    console.log(`${paint(C.cyan, '●')} ${msg}`);
  },
  success(msg) {
    console.log(`${paint(C.green, '✓')} ${msg}`);
  },
  warn(msg) {
    console.log(`${paint(C.yellow, '⚠')} ${msg}`);
  },
  error(msg) {
    console.error(`${paint(C.red, '✗')} ${msg}`);
  },
  dim(msg) {
    console.log(paint(C.dim, msg));
  },
  plain(msg = '') {
    console.log(msg);
  },
};

export { C, paint };
