#!/usr/bin/env node
/**
 * Termux 本地同步联系人(Node 版,无需 Python playwright)。
 *
 * 用 playwright-core(纯 JS 包)+ 系统 chromium(Termux x11-repo 的 chromium-browser)
 * 打开抖音私信页,滚动会话列表提取联系人,输出与 Python 版 douyin.sync_friends_page
 * 相同结构的 JSON:{"names":[{name,days,avatar,account}...],"error":null}
 *
 * 用法:node scripts/sync_friends.js --state <state.json 路径> [--max-rounds 20]
 * 环境变量:SPARK_CHROMIUM 指定 chromium 可执行文件路径(可选)
 * 结果 JSON 以 "RESULT:" 开头打印在 stdout 单独一行,其余日志走 stderr。
 */
"use strict";

const fs = require("fs");
const path = require("path");

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === "--state") args.state = argv[++i];
    else if (argv[i] === "--max-rounds") args.maxRounds = parseInt(argv[++i], 10) || 20;
  }
  return args;
}

function findChromium() {
  if (process.env.SPARK_CHROMIUM && fs.existsSync(process.env.SPARK_CHROMIUM)) {
    return process.env.SPARK_CHROMIUM;
  }
  const prefix = process.env.PREFIX || "/data/data/com.termux/files/usr";
  const candidates = [
    path.join(prefix, "bin", "chromium-browser"),
    path.join(prefix, "bin", "chromium"),
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
  ];
  for (const p of candidates) if (fs.existsSync(p)) return p;
  return null;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const EXTRACTOR_JS = `
() => {
    const out = [];
    const seen = new Set();
    const rows = document.querySelectorAll('[class*="conversationConversationItemwrapper"]');
    const cleanName = (el) => {
        const clone = el.cloneNode(true);
        clone.querySelectorAll(
            '[class*="TagNextToTitle"],[class*="timeStr"],[class*="streak"],[class*="Streak"],' +
            '[class*="badge"],[class*="commonStreak"],[class*="unread"],[class*="Unread"]'
        ).forEach(n => n.remove());
        return (clone.textContent || '').replace(/\\s+/g, ' ').trim();
    };
    for (const row of rows) {
        const rect = row.getBoundingClientRect();
        if (rect.height < 30 || rect.width < 100) continue;
        let name = '';
        let titleEl = row.querySelector('.conversationConversationItemtitle')
                   || row.querySelector('[class*="Itemtitle"]');
        if (titleEl) name = cleanName(titleEl);
        if (!name) {
            const aria = (row.getAttribute('aria-label') || '').trim();
            if (aria) name = aria.split(/[,\\n]/)[0].trim();
        }
        if (!name) name = cleanName(row);
        name = name.replace(/\\s*@[\\w.\\-]+$/, '').trim();
        if (!name || seen.has(name)) continue;
        if (/^\\d+$/.test(name) || /^\\d{1,2}:\\d{2}$/.test(name)) continue;
        if (name === '消息' || name === '私信' || name === '朋友私信' || name === '通知') continue;
        if (name.length > 40) continue;
        seen.add(name);
        let account = '';
        const sub = row.querySelector('[class*="ItemsubTitle"],[class*="subtitle"],[class*="Subtitle"]');
        const subText = sub ? (sub.textContent || '') : '';
        const mAcc = subText.match(/@([\\w.\\-]{2,})/) || (row.textContent || '').match(/@([\\w.\\-]{2,})/);
        if (mAcc) account = mAcc[1];
        let days = 0;
        const st = row.querySelector('[class*="commonStreak"],[class*="streakContainer"],[class*="Streak"]');
        if (st) {
            const mD = (st.textContent || '').match(/\\d+/);
            if (mD) days = parseInt(mD[0], 10);
        }
        if (!days) {
            const mD2 = (row.textContent || '').match(/🔥\\s*(\\d+)/);
            if (mD2) days = parseInt(mD2[1], 10);
        }
        let avatar = '';
        const imgs = row.querySelectorAll('img');
        for (const img of imgs) {
            const src = img.src || '';
            if (!src || src.includes('flame')) continue;
            const r2 = img.getBoundingClientRect();
            const size = r2.width || img.naturalWidth || 0;
            if (size >= 32) { avatar = src; break; }
        }
        if (!avatar) {
            for (const img of imgs) {
                const src = img.src || '';
                if (src && !src.includes('flame')) { avatar = src; break; }
            }
        }
        out.push({ name, days, avatar, account });
    }
    let atBottom = false;
    try {
        const scroller = document.querySelector('[class*="conversationList"],[class*="chatList"],[class*="ContactList"]');
        const el = (scroller && scroller.scrollHeight > scroller.clientHeight) ? scroller : document.scrollingElement;
        atBottom = el ? (el.scrollTop + el.clientHeight >= el.scrollHeight - 8) : true;
    } catch (e) {}
    return { items: out, atBottom };
}
`;

const LOGIN_MARKERS = ["扫码登录", "验证码登录", "登录后即可", "登录后查看"];
const CHAT_URL = "https://www.douyin.com/chat";
const USER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

function log(msg) {
  process.stderr.write(`[sync_friends] ${msg}\n`);
}

async function checkLogin(page, context) {
  const url = page.url();
  if (url.toLowerCase().includes("login") || url.toLowerCase().includes("passport")) {
    return `页面跳转到登录页(${url})`;
  }
  try {
    const qr = page.locator("#animate_qrcode_container");
    if ((await qr.count()) > 0 && (await qr.first().isVisible())) {
      return "页面出现扫码登录二维码,登录态已过期";
    }
  } catch (e) {}
  for (const text of LOGIN_MARKERS) {
    try {
      const loc = page.getByText(text);
      const n = Math.min(await loc.count(), 3);
      for (let i = 0; i < n; i++) {
        if (await loc.nth(i).isVisible()) return `页面出现登录提示「${text}」`;
      }
    } catch (e) {}
  }
  try {
    const cookies = await context.cookies();
    if (!cookies.some((c) => (c.name || "").startsWith("sessionid"))) {
      return "未检测到 sessionid Cookie";
    }
  } catch (e) {
    return "无法读取 Cookie";
  }
  return null;
}

async function openChat(page, retries) {
  for (let i = 0; i < retries; i++) {
    try {
      await page.goto(CHAT_URL, { timeout: 90000, waitUntil: "domcontentloaded" });
      return true;
    } catch (e) {
      log(`打开聊天页失败(第 ${i + 1} 次): ${String(e).slice(0, 80)}`);
      await sleep(5000);
    }
  }
  return false;
}

async function fetchConversations(page, maxRounds) {
  const collected = [];
  let stable = 0;
  for (let round = 0; round < maxRounds; round++) {
    let result = {};
    try {
      result = (await page.evaluate(EXTRACTOR_JS)) || {};
    } catch (e) {}
    const items = result.items || [];
    const key = (x) => `${x.name}|${x.days}|${x.account}`;
    const known = new Set(collected.map(key));
    const fresh = items.filter((x) => !known.has(key(x)));
    if (fresh.length) {
      collected.push(...fresh);
      stable = 0;
    } else {
      stable += 1;
      if (stable >= 2 || result.atBottom) break;
    }
    if (result.atBottom) break;
    try {
      await page.mouse.move(220, 380);
      await page.mouse.wheel(0, 450);
    } catch (e) {}
    await sleep(350);
  }
  return collected;
}

async function main() {
  const args = parseArgs(process.argv);
  const result = { names: [], error: null };

  if (!args.state || !fs.existsSync(args.state)) {
    result.error = "该账号尚未上传登录态 state.json";
    console.log(`RESULT:${JSON.stringify(result)}`);
    return 1;
  }
  let playwright;
  try {
    playwright = require("playwright-core");
  } catch (e) {
    result.error = "未安装 playwright-core:cd ~/spark-cloud && npm install playwright-core";
    console.log(`RESULT:${JSON.stringify(result)}`);
    return 1;
  }
  const exe = findChromium();
  if (!exe) {
    result.error =
      "找不到 chromium:pkg install x11-repo -y && pkg install chromium -y,或 export SPARK_CHROMIUM=/路径/chromium";
    console.log(`RESULT:${JSON.stringify(result)}`);
    return 1;
  }
  log(`chromium: ${exe}`);

  let browser = null;
  try {
    browser = await playwright.chromium.launch({
      executablePath: exe,
      headless: true,
      args: [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
      ],
    });
    const context = await browser.newContext({
      viewport: { width: 1366, height: 768 },
      userAgent: USER_AGENT,
      locale: "zh-CN",
      timezoneId: "Asia/Shanghai",
      ignoreHTTPSErrors: true,
      storageState: args.state,
    });
    const page = await context.newPage();

    if (!(await openChat(page, 3))) {
      result.error = "无法打开抖音私信页面";
      return 1;
    }
    await sleep(3000);
    const loginErr = await checkLogin(page, context);
    if (loginErr) {
      result.error = loginErr;
      return 1;
    }

    let collected = [];
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        await page.waitForSelector(".conversationConversationItemtitle", { timeout: 45000 });
      } catch (e) {}
      await sleep(4000);
      collected = await fetchConversations(page, args.maxRounds || 20);
      if (collected.length >= 3) break;
      try {
        await page.reload({ waitUntil: "domcontentloaded", timeout: 90000 });
        await sleep(10000);
      } catch (e) {
        break;
      }
    }
    result.names = collected;
    log(`同步完成:${collected.length} 个联系人`);
    return 0;
  } catch (e) {
    result.error = `同步联系人异常: ${String(e).slice(0, 200)}`;
    return 1;
  } finally {
    if (browser) {
      try {
        await browser.close();
      } catch (e) {}
    }
    console.log(`RESULT:${JSON.stringify(result)}`);
  }
}

main().then((code) => process.exit(code));
