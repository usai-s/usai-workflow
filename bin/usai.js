#!/usr/bin/env node
/**
 * usai-workflow installer — ставит AI workflow в целевой проект.
 *
 * Движок ничего не знает о конкретных модулях: каждый модуль описан
 * манифестом `module.json` и каталогом `files/`, зеркалящим целевую
 * раскладку. Добавить модуль = добавить каталог в `modules/`; код движка
 * не меняется.
 *
 * Использование:
 *   npx usai-workflow --target <путь-к-проекту>          # диалог
 *   npx usai-workflow --target <путь> --all --yes        # всё, без вопросов
 *   npx usai-workflow --target <путь> --modules adapter-claude --yes
 *   npx usai-workflow --list                             # список модулей
 *   npx usai-workflow --target <путь> --dry-run --all    # показать план
 *
 * Поведение при конфликте: существующий файл с другим содержимым
 * останавливает установку ДО первой записи (двухфазный план). `--force`
 * перезаписывает. Файлы из списка `seed` манифеста — проектные заготовки
 * (AGENTS.md, конфиг verify и т.п.): создаются только если их ещё нет,
 * существующие не трогаются и конфликтом не считаются.
 *
 * После установки в целевом проекте появляется `.usai-workflow.lock` —
 * версия, список модулей и sha256 каждого поставленного файла (задел
 * для `update`).
 *
 * Требования: Node.js >= 18, без зависимостей.
 */

"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");
const LOCK_NAME = ".usai-workflow.lock";

function fail(message) {
  process.stderr.write(message + "\n");
  process.exit(1);
}

// ---------- Модули ----------

function loadModule(moduleRoot) {
  const manifestPath = path.join(moduleRoot, "module.json");
  let data;
  try {
    data = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  } catch (error) {
    fail(`${manifestPath}: не читается JSON: ${error.message}`);
  }
  for (const key of ["id", "title", "description"]) {
    if (!data[key]) fail(`${manifestPath}: отсутствует обязательное поле "${key}"`);
  }
  const filesDir = path.join(moduleRoot, "files");
  if (!fs.existsSync(filesDir) || !fs.statSync(filesDir).isDirectory()) {
    fail(`${moduleRoot}: нет каталога files/`);
  }
  return {
    id: data.id,
    title: data.title,
    description: data.description,
    requires: data.requires ?? [],
    seed: data.seed ?? [],
    always: Boolean(data.always),
    question: data.question ?? "",
    filesDir,
  };
}

function discover() {
  const roots = [path.join(ROOT, "core")];
  const modulesDir = path.join(ROOT, "modules");
  if (fs.existsSync(modulesDir)) {
    for (const name of fs.readdirSync(modulesDir).sort()) {
      roots.push(path.join(modulesDir, name));
    }
  }
  const modules = new Map();
  for (const root of roots) {
    if (!fs.existsSync(path.join(root, "module.json"))) continue;
    const m = loadModule(root);
    if (modules.has(m.id)) fail(`дубль id модуля: ${m.id}`);
    modules.set(m.id, m);
  }
  if (!modules.has("core")) fail("не найден core/module.json — пакет повреждён?");
  return modules;
}

function resolveSelection(modules, wanted) {
  const seen = [];
  const add = (id) => {
    if (seen.includes(id)) return;
    const m = modules.get(id);
    if (!m) {
      fail(`неизвестный модуль "${id}"; доступны: ${[...modules.keys()].sort().join(", ")}`);
    }
    for (const dep of m.requires) add(dep);
    seen.push(id);
  };
  add("core");
  for (const id of wanted) add(id);
  return seen.map((id) => modules.get(id));
}

// ---------- План файлов ----------

function walkFiles(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walkFiles(full));
    else if (entry.isFile()) out.push(full);
  }
  return out;
}

function planFiles(selection) {
  const planned = [];
  const owners = new Map();
  for (const m of selection) {
    const seeds = new Set(m.seed);
    for (const src of walkFiles(m.filesDir)) {
      const rel = path.relative(m.filesDir, src).split(path.sep).join("/");
      if (owners.has(rel)) {
        fail(`файл ${rel} есть и в ${owners.get(rel)}, и в ${m.id} — модули не должны пересекаться по файлам`);
      }
      owners.set(rel, m.id);
      planned.push({ src, rel, module: m.id, isSeed: seeds.has(rel) });
    }
  }
  return planned;
}

function sha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

// ---------- Установка ----------

function install(target, selection, planned, { force, dryRun }) {
  const conflicts = [];
  const toCopy = [];
  const skippedSeeds = [];
  let identical = 0;

  for (const pf of planned) {
    const dst = path.join(target, pf.rel);
    if (fs.existsSync(dst)) {
      if (pf.isSeed) {
        skippedSeeds.push(pf.rel);
        continue;
      }
      if (sha256(dst) === sha256(pf.src)) {
        identical += 1;
        continue;
      }
      if (!force) {
        conflicts.push(pf.rel);
        continue;
      }
    }
    toCopy.push(pf);
  }

  if (conflicts.length > 0) {
    process.stderr.write("Установка остановлена: конфликты (файл существует и отличается):\n");
    for (const rel of conflicts) process.stderr.write(`  ${rel}\n`);
    process.stderr.write("Ничего не записано. Разберитесь с файлами или используйте --force.\n");
    return 1;
  }

  const verb = dryRun ? "будет записан" : "записан";
  for (const pf of toCopy) {
    console.log(`  ${verb}: ${pf.rel}  [${pf.module}]`);
    if (!dryRun) {
      const dst = path.join(target, pf.rel);
      fs.mkdirSync(path.dirname(dst), { recursive: true });
      fs.copyFileSync(pf.src, dst);
      fs.chmodSync(dst, fs.statSync(pf.src).mode);
    }
  }
  for (const rel of skippedSeeds) console.log(`  оставлен как есть (seed): ${rel}`);
  if (identical > 0) console.log(`  без изменений: ${identical} файл(ов)`);

  if (dryRun) {
    console.log(`\n(dry-run) файлов к записи: ${toCopy.length}`);
    return 0;
  }

  const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8"));
  const lock = {
    version: pkg.version,
    modules: selection.map((m) => m.id),
    files: Object.fromEntries(
      planned.filter((pf) => !pf.isSeed).map((pf) => [pf.rel, { sha256: sha256(pf.src), module: pf.module }])
    ),
    seeds: planned.filter((pf) => pf.isSeed).map((pf) => pf.rel).sort(),
  };
  fs.writeFileSync(path.join(target, LOCK_NAME), JSON.stringify(lock, null, 2) + "\n", "utf8");
  console.log(`\nГотово: ${toCopy.length} файл(ов), lock — ${LOCK_NAME}.`);
  console.log("Дальше: заполните AGENTS.md (слоты проекта) и scripts/verify.config.sh.");
  return 0;
}

// ---------- CLI ----------

function parseArgs(argv) {
  const args = { modules: null, yes: false, all: false, force: false, dryRun: false, list: false, target: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case "--target": args.target = argv[++i]; break;
      case "--modules": args.modules = argv[++i]; break;
      case "--all": args.all = true; break;
      case "--yes": case "-y": args.yes = true; break;
      case "--force": args.force = true; break;
      case "--dry-run": args.dryRun = true; break;
      case "--list": args.list = true; break;
      case "-h": case "--help": args.help = true; break;
      default: fail(`неизвестный аргумент: ${a} (справка: --help)`);
    }
  }
  return args;
}

const HELP = `Установка usai-workflow в проект.

  npx usai-workflow --target <каталог>            диалог выбора модулей
  npx usai-workflow --target <каталог> --all -y   все модули без вопросов
  npx usai-workflow --target <каталог> --modules <id,id> -y
  npx usai-workflow --list                        список модулей

Флаги: --force (перезаписывать отличающиеся файлы), --dry-run (только план).`;

async function interactiveSelection(modules) {
  const readline = require("node:readline/promises");
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const wanted = [];
  const optional = [...modules.values()].filter((m) => !m.always);
  if (optional.length > 0) console.log("Выберите модули (ядро ставится всегда):\n");
  try {
    for (const m of optional) {
      const question = m.question || `Установить модуль «${m.title}»?`;
      const note = m.requires.length > 0 ? ` (требует: ${m.requires.join(", ")})` : "";
      console.log(`  ${m.id} — ${m.description}`);
      for (;;) {
        const answer = (await rl.question(`  ${question}${note} [Y/n] `)).trim().toLowerCase();
        if (answer === "" || ["y", "yes", "д", "да"].includes(answer)) { wanted.push(m.id); break; }
        if (["n", "no", "н", "нет"].includes(answer)) break;
        console.log("  ответьте y или n");
      }
      console.log("");
    }
  } finally {
    rl.close();
  }
  return wanted;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) { console.log(HELP); return 0; }

  const modules = discover();

  if (args.list) {
    for (const m of modules.values()) {
      const mark = m.always ? "всегда" : "опция";
      const deps = m.requires.length > 0 ? `, требует: ${m.requires.join(", ")}` : "";
      console.log(`  ${m.id.padEnd(16)} [${mark}${deps}] ${m.description}`);
    }
    return 0;
  }

  if (!args.target) fail("нужен --target (или --list); справка: --help");
  const target = path.resolve(args.target);
  if (!fs.existsSync(target) || !fs.statSync(target).isDirectory()) {
    fail(`целевой каталог не существует: ${target}`);
  }

  let wanted;
  if (args.all) wanted = [...modules.keys()];
  else if (args.modules) wanted = args.modules.split(",").map((x) => x.trim()).filter(Boolean);
  else if (args.yes) fail("--yes без --all/--modules: непонятно, что ставить");
  else wanted = await interactiveSelection(modules);

  const selection = resolveSelection(modules, wanted);
  console.log(`\nУстановка в ${target}: ${selection.map((m) => m.id).join(", ")}\n`);
  const planned = planFiles(selection);
  return install(target, selection, planned, { force: args.force, dryRun: args.dryRun });
}

main().then(
  (code) => process.exit(code),
  (error) => fail(String(error && error.stack ? error.stack : error))
);
