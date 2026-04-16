import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI情报中台",
  description: "小红书爆款笔记监控系统",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="bg-gray-50 text-gray-900 antialiased">{children}</body>
    </html>
  );
}
