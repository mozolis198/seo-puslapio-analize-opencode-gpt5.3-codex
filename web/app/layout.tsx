import "./globals.css";
import type { Metadata } from "next";
import { Libre_Baskerville, Manrope } from "next/font/google";

const manrope = Manrope({ subsets: ["latin"], variable: "--font-sans" });
const libreBaskerville = Libre_Baskerville({ subsets: ["latin"], weight: ["400", "700"], variable: "--font-serif" });

export const metadata: Metadata = {
  title: "SEO Analyzer",
  description: "Hybrid SEO analyzer starter"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${manrope.variable} ${libreBaskerville.variable}`}>{children}</body>
    </html>
  );
}
