import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import { ThemeToggle } from "@/components/theme-toggle";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const mono = JetBrains_Mono({ variable: "--font-mono-face", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "AV Recovery Desk",
  description: "Triage for UK insurers: which autonomous-vehicle claims can be recovered from the AV company, and how much.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB" className={`${inter.variable} ${mono.variable} antialiased`} suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem("theme");if(t==="dark"||t==="light")document.documentElement.setAttribute("data-theme",t)}catch(e){}`,
          }}
        />
      </head>
      <body className="min-h-screen font-sans">
        <header className="border-b border-line bg-panel">
          <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3 sm:px-6">
            <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
              <span aria-hidden className="inline-block h-5 w-5 rounded-sm bg-accent" />
              AV Recovery Desk
            </Link>
            <nav className="flex items-center gap-4 text-sm text-muted">
              <Link href="/run" className="hover:text-fg">Agent run</Link>
              <Link href="/" className="hover:text-fg">Claims</Link>
              <Link href="/new" className="hover:text-fg">New claim</Link>
            </nav>
            <div className="ml-auto flex items-center gap-3">
              <span className="hidden text-xs text-muted sm:inline">Triage, not a ruling</span>
              <ThemeToggle />
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">{children}</main>
        <footer className="mx-auto max-w-7xl px-4 pb-10 pt-4 text-xs text-muted sm:px-6">
          Decision support for a human claims handler under AEVA 2018 s.2 and s.5. Not a liability ruling and not legal
          advice. Example claims are synthetic. Public data only; no personal data is stored.
        </footer>
      </body>
    </html>
  );
}
