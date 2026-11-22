import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "실록 날짜 타임라인", template: "%s · 실록 날짜 타임라인" },
  description: "조선왕조실록 기사를 날짜별로 — 양력·음력·왕력·간지를 함께 보여 줍니다.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;600&display=swap"
        />
      </head>
      <body>
        <header className="site">
          <Link href="/" className="brand">실록 날짜 타임라인</Link>
          <span className="sub">조선왕조실록 · 선조 25~31년 (1592~1598)</span>
        </header>
        <main>{children}</main>
        <footer className="site">
          <p>
            원문: 국사편찬위원회 「조선왕조실록 원문」(공공데이터포털, 공공누리 제1유형). 요약과 해설은 이 사이트가 원문에서
            직접 만든 것이며 국사편찬위원회 번역문이 아닙니다. 요약은 검수 전 초안입니다.
          </p>
          <p>양력은 1582년 10월 15일 이후 그레고리력, 그 전은 율리우스력입니다. 음력은 한국천문연구원 자료 기반 표로 계산했습니다.</p>
        </footer>
      </body>
    </html>
  );
}
