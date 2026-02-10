import "./globals.css";
import type { Metadata } from "next";
import { Libre_Baskerville, Manrope } from "next/font/google";

const manrope = Manrope({ subsets: ["latin"], variable: "--font-sans" });
const libreBaskerville = Libre_Baskerville({ subsets: ["latin"], weight: ["400", "700"], variable: "--font-serif" });

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "https://seo-puslapio-analize-opencode-gpt5.vercel.app"),
  title: "SEO puslapio analize ir veiksmu planas | Opencode GPT5",
  description:
    "Atlik SEO puslapio analize, gauk techniniu klaidu isvadas ir prioritetuota veiksmu plana matomumui gerinti paieskoje.",
  alternates: {
    canonical: "/"
  },
  openGraph: {
    title: "SEO puslapio analize ir veiksmu planas",
    description:
      "Atlik SEO puslapio analize ir gauk aisku prioritetu plana: technines klaidos, turinio kokybe, indeksavimo signalai ir pataisymai.",
    url: "/",
    siteName: "SEO Puslapio Analize",
    type: "website",
    locale: "lt_LT"
  },
  twitter: {
    card: "summary_large_image",
    title: "SEO puslapio analize ir veiksmu planas",
    description:
      "Praktinis SEO auditas su TOP checklist ir prioritetais: dabar, sia savaite, veliau."
  }
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${manrope.variable} ${libreBaskerville.variable}`}>{children}</body>
    </html>
  );
}
