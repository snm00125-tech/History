// 배포 전 화면 점검: 빌드한 사이트(out/)를 띄워 주요 화면이 오류 없이 뜨는지 본다.
//   cd web && npm run build && node scripts/smoke.cjs
// Playwright(chromium)가 필요하다(클라우드 세션에는 깔려 있음: NODE_PATH=$(npm root -g)).
const { chromium } = require("playwright");
const http = require("http");
const fs = require("fs");
const path = require("path");

const OUT = path.join(__dirname, "..", "out");
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".woff2": "font/woff2" };

function serve() {
  return http.createServer((req, res) => {
    let p = decodeURIComponent(req.url.split("?")[0]);
    if (p.endsWith("/")) p += "index.html";
    let f = path.join(OUT, p);
    if (!fs.existsSync(f) && fs.existsSync(f + ".html")) f += ".html";
    if (!f.startsWith(OUT) || !fs.existsSync(f)) {
      res.writeHead(404);
      return res.end("not found");
    }
    res.writeHead(200, { "content-type": TYPES[path.extname(f)] || "application/octet-stream" });
    fs.createReadStream(f).pipe(res);
  }).listen(0);
}

const CHECKS = [
  ["첫 화면", "/", ".eras li"],
  ["날짜 화면", "/view/?ym=1592-05&d=23", ".card"],
  ["고종 양력", "/view/?ym=1896-01&d=1", ".card"],
  ["제목 검색", "/search/?q=" + encodeURIComponent("거북선"), ".results li"],
  ["인물 검색", "/search/?q=" + encodeURIComponent("이순신"), ".plist li"],
  ["원문 검색", "/search/?mode=text&q=" + encodeURIComponent("龜船"), ".fthits li"],
  ["인물 화면", "/person/?id=M_0004641", ".personview .results li"],
  ["왕별 연표", "/kings/", ".krow"],
  ["날짜 검수", "/review/", ".rg-title"],
  ["용어 사전", "/terms/", ".termlist dt"],
  ["연도별 도식", "/timeline/", ".tl-svg rect"],
  ["기원전 날짜", "/view/?ym=-057-05", ".card"],
  ["고려 날짜", "/view/?ym=1019-03", ".card"],
  ["지도", "/map/", ".map-dot"],
];

(async () => {
  const server = serve();
  const base = `http://localhost:${server.address().port}`;
  const browser = await chromium.launch();
  let bad = 0;
  for (const [name, url, sel] of CHECKS) {
    const page = await browser.newPage();
    const errs = [];
    page.on("pageerror", (e) => errs.push(String(e)));
    const t0 = Date.now();
    try {
      await page.goto(base + url, { waitUntil: "domcontentloaded" });
      await page.waitForSelector(sel, { timeout: 30000 });
      const ms = Date.now() - t0;
      const ok = !errs.length;
      if (!ok) bad++;
      console.log(`${ok ? "통과" : "오류"}  ${name}  ${ms}ms${errs.length ? "  " + errs[0] : ""}`);
    } catch (e) {
      bad++;
      console.log(`실패  ${name}  ${String(e).split("\n")[0]}`);
    }
    await page.close();
  }
  await browser.close();
  server.close();
  console.log(bad ? `문제 ${bad}개` : "모두 통과");
  process.exit(bad ? 1 : 0);
})();
