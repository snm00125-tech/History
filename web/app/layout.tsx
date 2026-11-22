import type { Metadata } from "next";
import Link from "next/link";
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "조선 기록 날짜별 보기",
  description: "조선왕조실록·비변사등록 등 조선 기록을 날짜별로 보는 개인용 타임라인",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <header className="top">
          <div className="top-inner">
          <Link href="/" className="brand">
            조선 기록 <span>날짜별 보기</span>
          </Link>
          <nav className="topnav">
            <Link href="/search/">검색</Link>
            <Link href="/kings/">왕별 연표</Link>
          </nav>
          </div>
        </header>
        <main>{children}</main>
        <footer className="foot">
          원문·국문 제목: 국사편찬위원회 조선왕조실록·한국사데이터베이스(공공데이터포털). 요약은 이 앱에서 원문을 보고 만든 것이다. 개인용.
        </footer>
      </body>
    </html>
  );
}
