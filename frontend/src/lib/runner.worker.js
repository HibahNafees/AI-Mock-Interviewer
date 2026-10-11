// Runs the candidate's code off the page: Python through Pyodide (loaded from
// the jsDelivr CDN on first use, then cached by the browser) and JavaScript
// natively. The page terminates this worker on a timeout, so an endless loop
// can't freeze the interview.
/* global loadPyodide, importScripts */

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
let pyodide = null;

function send(type, text = "") {
  self.postMessage({ type, text });
}

function show(value) {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

async function runPython(code) {
  if (!pyodide) {
    send("status", "Loading Python (first run only, a few seconds)…");
    importScripts(`${PYODIDE}pyodide.js`);
    pyodide = await loadPyodide({ indexURL: PYODIDE });
  }
  pyodide.setStdout({ batched: (line) => send("out", `${line}\n`) });
  pyodide.setStderr({ batched: (line) => send("err", `${line}\n`) });
  pyodide.setStdin({ error: true });
  send("started");
  const scope = pyodide.globals.get("dict")();
  try {
    const result = await pyodide.runPythonAsync(code, { globals: scope });
    if (result !== undefined && result !== null) send("out", `${result}\n`);
  } finally {
    scope.destroy();
  }
}

async function runJavaScript(code) {
  const log =
    (type) =>
    (...args) =>
      send(type, `${args.map(show).join(" ")}\n`);
  self.console.log = log("out");
  self.console.info = log("out");
  self.console.warn = log("err");
  self.console.error = log("err");
  send("started");
  await new Function(`return (async () => {\n${code}\n})()`)();
}

self.onmessage = async ({ data }) => {
  try {
    if (data.language === "python") await runPython(data.code);
    else await runJavaScript(data.code);
    send("done");
  } catch (err) {
    // Python errors carry the whole traceback; keep its useful tail.
    const text = String(err?.message ?? err);
    const at = text.lastIndexOf('File "<exec>"');
    let shown = at >= 0 ? text.slice(at) : text;
    if (shown.includes("[Errno 29]"))
      shown += "input() can't read here: put your test values in the code.\n";
    send("error", shown);
  }
};
