import type { ReactNode } from "react";
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Local Figma 워크스페이스",
  description: "채팅, 프리뷰, 런타임 상태를 갖춘 오퍼레이터 워크스페이스.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
