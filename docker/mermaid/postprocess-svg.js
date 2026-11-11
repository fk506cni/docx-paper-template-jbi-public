#!/usr/bin/env node
// postprocess-svg.js — mmdc が出した SVG を Office (Word / PowerPoint) と librsvg が正しく描けるように直す。
// convert.sh が mermaid コンテナ内で実行する (node のみ。依存なし)。
//
// 使い方: node postprocess-svg.js <file.svg>   (その場で書き換える)
//
// 1. hsl() / hsla() の色を 16 進 (#rrggbb) に直す
//    Mermaid はテーマの色を変えると、サブグラフの枠・辺のラベルなどの色を hsl() で算出する
//    (例: theme "base" で primaryColor だけ指定すると .cluster rect が hsl(24, 76.9%, 99.9%) になる)。
//    PowerPoint はこの色を解釈できず**箱を黒く塗る** (Microsoft 365 で実測。CSS のクラスで塗っても
//    fill 属性に書き写しても同じだった = 原因は塗り方ではなく色の書き方)。
//    透明度つき (hsla の a < 1) は rgba() にする (Office の rgba 対応は未確認なので、16 進に潰して
//    透明度を黙って捨てることはしない)。
// 2. 小数の rgb() を 16 進に直す
//    同じ条件で Mermaid は rgb(0.0577, 0.2885, 0.4423) のような 0〜1 の値を出す (0〜255 のつもりでない値)。
//    ブラウザはこれを四捨五入してほぼ黒 (#000000) で描くので、その見た目に合わせて 16 進にする。
//    整数の rgb() は PowerPoint でも正しく描かれた (classDef の塗り) ので触らない。
// 3. <text> に xml:space="preserve" を付ける
//    htmlLabels:false のラベルは 1 語ずつ <tspan> に分かれ、2 語目以降が先頭に空白を持つ。librsvg (PNG
//    フォールバックの描画系) はこの空白を落とし `apparatusbody` になる。Mermaid の出力は <text> の中に
//    改行・字下げを含まないので、preserve で余計な空白は増えない。
'use strict';
const fs = require('fs');

const file = process.argv[2];
if (!file) {
    console.error('使い方: node postprocess-svg.js <file.svg>');
    process.exit(2);
}
let svg = fs.readFileSync(file, 'utf8');

const clamp = (v) => Math.max(0, Math.min(255, Math.round(v)));
const hex = (r, g, b) => '#' + [r, g, b].map((v) => clamp(v).toString(16).padStart(2, '0')).join('');

function hslToRgb(h, s, l) {
    h = (((h % 360) + 360) % 360) / 360;
    s = Math.max(0, Math.min(1, s));
    l = Math.max(0, Math.min(1, l));
    if (s === 0) return [l * 255, l * 255, l * 255];
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    const f = (t) => {
        if (t < 0) t += 1;
        if (t > 1) t -= 1;
        if (t < 1 / 6) return p + (q - p) * 6 * t;
        if (t < 1 / 2) return q;
        if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
        return p;
    };
    return [f(h + 1 / 3) * 255, f(h) * 255, f(h - 1 / 3) * 255];
}

let nHsl = 0;
let nRgb = 0;
let nText = 0;

// hsl(24, 76.9%, 99.9%) / hsl(24deg 76.9% 99.9%) / hsla(24, 76.9%, 99.9%, 0.5) / hsl(24 76.9% 99.9% / 50%)
svg = svg.replace(
    /hsla?\(\s*(-?[\d.]+)(?:deg)?\s*[,\s]\s*([\d.]+)%\s*[,\s]\s*([\d.]+)%\s*(?:[,/]\s*([\d.]+)(%?)\s*)?\)/gi,
    (m, h, s, l, a, pct) => {
        const [r, g, b] = hslToRgb(parseFloat(h), parseFloat(s) / 100, parseFloat(l) / 100);
        nHsl += 1;
        if (a !== undefined) {
            const alpha = pct ? parseFloat(a) / 100 : parseFloat(a);
            if (alpha < 1) return `rgba(${clamp(r)}, ${clamp(g)}, ${clamp(b)}, ${alpha})`;
        }
        return hex(r, g, b);
    },
);

// rgb(0.0577, 0.2885, 0.4423) のように小数を含むものだけ
svg = svg.replace(/rgb\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\)/gi, (m, r, g, b) => {
    if ([r, g, b].every((v) => /^\d+$/.test(v))) return m;
    nRgb += 1;
    return hex(parseFloat(r), parseFloat(g), parseFloat(b));
});

svg = svg.replace(/<text(?![^>]*\bxml:space=)([\s>])/g, (m, c) => {
    nText += 1;
    return `<text xml:space="preserve"${c}`;
});

fs.writeFileSync(file, svg);
console.log(`  後処理: hsl() → 16 進 ${nHsl} 個 / 小数の rgb() → 16 進 ${nRgb} 個 / ` +
            `<text> に xml:space="preserve" ${nText} 個`);
