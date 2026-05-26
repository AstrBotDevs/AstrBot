import type { HeadConfig } from "vitepress";

export const head: HeadConfig[] = [
    // --- Google Fonts ---
    ["link", { rel: "preconnect", href: "https://fonts.googleapis.cn", crossorigin: "" }],
    ["link", { rel: "dns-prefetch", href: "https://fonts.googleapis.cn" }],
    ["link", { rel: "preconnect", href: "https://fonts.gstatic.cn", crossorigin: "" }],
    ["link", { rel: "dns-prefetch", href: "https://fonts.gstatic.cn" }],
    ["link", { rel: "stylesheet", href: "https://fonts.googleapis.com/css2?family=Outfit:wght@100..900&display=swap" }],

    // --- 基础和SEO元数据 ---
    ["link", { rel: "icon", href: "/logo.png" }],
    ["meta", { name: "description", content: "AstrBot" }],
    [
        "meta",
        { name: "viewport", content: "width=device-width, initial-scale=1.0" },
    ],

  /*  // --- Open Graph (OG) 协议元数据 (用于社交媒体分享) ---
    ["meta", { property: "og:type", content: "website" }],
    ["meta", { property: "og:locale", content: "zh_CN" }],
    ["meta", { property: "og:title", content: "AstrBot" }],
    ["meta", { property: "og:description", content: "AstrBot" }],
    ["meta", { property: "og:url", content: "https://docs.astrbot.app" }],
    ["meta", { property: "og:site_name", content: "AstrBot" }],
    [
        "meta",
        {
            property: "og:image",
            content: "/",
        },
    ],
    [
        "meta",
        { property: "og:image:alt", content: "AstrBot" },
    ],
    ["meta", { property: "og:image:width", content: "1200" }],
    ["meta", { property: "og:image:height", content: "630" }],
    ["meta", { property: "og:image:type", content: "image/png" }],

    // --- Twitter Card 元数据 ---
    ["meta", { name: "twitter:card", content: "summary_large_image" }],
    ["meta", { name: "twitter:site", content: "@AstrBot" }],*/

    // --- Umami Analytics ---
    ["script", { defer: "", src: "https://cloud.umami.is/script.js", "data-website-id": "9c3f777e-9f4a-4b79-a5c3-ff94f5dca8f9" }],
];