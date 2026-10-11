// Runs code from the editor in a Web Worker (see runner.worker.js) and collects
// what it prints. Nothing is sent to the server, and nothing costs money.

export const RUNNABLE = { python: "Python", javascript: "JavaScript" };
const RUN_LIMIT_MS = 5000; // once the code starts; loading Python doesn't count
const LOAD_LIMIT_MS = 60000;
const MAX_OUTPUT = 20000;

let worker = null;
let finishCurrent = null;

function fresh() {
  worker?.terminate();
  worker = new Worker(new URL("./runner.worker.js", import.meta.url));
  return worker;
}

function dropWorker() {
  worker?.terminate();
  worker = null;
}

// Stops the running program. The loaded Python goes with it (reloaded next run).
export function stopRun() {
  if (finishCurrent) finishCurrent({ stopped: true });
  else dropWorker();
}

// onStatus(text) reports loading. Resolves to { output, error, timedOut, stopped }.
export function runCode(
  language,
  code,
  { onStatus = () => {}, onOutput = () => {} } = {},
) {
  const w = worker ?? fresh();
  return new Promise((resolve) => {
    let output = "";
    let timer = setTimeout(
      () =>
        finish({
          error:
            "Python took too long to load. Check your connection and try again.",
        }),
      LOAD_LIMIT_MS,
    );
    function finish(extra) {
      clearTimeout(timer);
      w.onmessage = null;
      w.onerror = null;
      finishCurrent = null;
      if (extra.timedOut || extra.stopped || extra.crashed) dropWorker();
      resolve({ output, error: "", timedOut: false, stopped: false, ...extra });
    }
    const add = (text) => {
      if (output.length < MAX_OUTPUT)
        output = (output + text).slice(0, MAX_OUTPUT);
      onOutput(output);
    };
    w.onmessage = ({ data }) => {
      if (data.type === "status") onStatus(data.text);
      else if (data.type === "started") {
        onStatus("");
        clearTimeout(timer);
        timer = setTimeout(() => finish({ timedOut: true }), RUN_LIMIT_MS);
      } else if (data.type === "out" || data.type === "err") add(data.text);
      else if (data.type === "done") finish({});
      else if (data.type === "error") finish({ error: data.text });
    };
    w.onerror = (e) => {
      e.preventDefault?.();
      finish({ error: e.message || "The code could not run.", crashed: true });
    };
    finishCurrent = finish;
    w.postMessage({ language, code });
  });
}
