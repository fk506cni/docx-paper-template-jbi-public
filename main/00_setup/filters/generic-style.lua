-- generic-style.lua: 共通スタイル付与フィルタ (build / diff 共用)
--
-- 役割は 3 つ:
--   (1) 画像パス `*.svg` → `*.svg.png` 書換 (pandoc 段は PNG フォールバックを参照する。
--       ネイティブ SVG 埋込は後処理 postprocess.py の wrap_textboxes() が別途行う。docs/architecture.md §2.1)
--   (2) custom-style Div の温存 (タイトル/著者/抄録等)。本文 Para は任意で body-style に包む
--   (3) .textbox / .grid マーカーの emit (後処理 postprocess.py の wrap_textboxes() が消費する)
--
-- 雑誌非依存にするため「本文段落を包む custom-style 名」はメタ変数 `body-style` から取る。
--   - body-style 未設定 (既定): 本文 Para は包まない (reference.docx の Normal が体裁を持つ。_default はこれ)
--   - body-style 設定時      : 最上位の素の Para を custom-style=<body-style> の Div で包む
--                              (雑誌テンプレが固有の本文段落スタイルを要求する場合に使う)
--
-- docx 出力時のみ有効。Pandoc レベルで処理し、custom-style Div 内の Para を二重に包まない。

if FORMAT ~= "docx" then
  return {}
end

--- Div が custom-style 属性を持つか
local function has_custom_style(div)
  return div.attributes and div.attributes["custom-style"] ~= nil
end

--- 寸法文字列 (例 "80mm", "300pt") を EMU へ変換
--- 1mm=36000 EMU, 1pt=12700 EMU, 1cm=360000 EMU, 1in=914400 EMU
--- 不正入力 (前後空白・大文字単位・単位省略・負値・多重小数 "1.2.3mm") を堅牢に扱う。
--- 解釈不能なら警告を出して 0 を返す (黙って 0 にすると寸法の誤りに気づけない)。
local function to_emu(s)
  if not s then return 0 end
  s = tostring(s)
  s = s:match("^%s*(.-)%s*$") or s          -- 前後空白を除去
  if s == "" then return 0 end
  local num, unit = s:match("^(%-?[%d%.]+)%s*(%a*)$")
  if not num then
    io.stderr:write("警告: 寸法を解釈できません: '" .. s .. "' -> 0 を使用\n")
    return 0
  end
  local n = tonumber(num)                    -- "1.2.3" 等は nil
  if not n then
    io.stderr:write("警告: 不正な数値の寸法: '" .. s .. "' -> 0 を使用\n")
    return 0
  end
  if n < 0 then
    io.stderr:write("警告: 負の寸法は不可: '" .. s .. "' -> 0 を使用\n")
    return 0
  end
  unit = unit:lower()                        -- "MM" -> "mm"
  if unit == "mm" then return math.floor(n * 36000)
  elseif unit == "pt" then return math.floor(n * 12700)
  elseif unit == "cm" then return math.floor(n * 360000)
  elseif unit == "in" then return math.floor(n * 914400)
  elseif unit == "emu" or unit == "" then return math.floor(n)
  else
    io.stderr:write("警告: 未知の寸法単位 '" .. unit .. "' (" .. s .. ") -> EMU として扱う\n")
    return math.floor(n)
  end
end

--- TextBoxMarker な隠し段落 (後処理が境界として読む) を作る
local function textbox_marker(text)
  return pandoc.RawBlock("openxml",
    '<w:p><w:pPr><w:pStyle w:val="TextBoxMarker"/></w:pPr>' ..
    '<w:r><w:rPr><w:vanish/></w:rPr>' ..
    '<w:t xml:space="preserve">' .. text .. '</w:t></w:r></w:p>')
end

-- 本文段落を包む custom-style 名 (Pandoc ハンドラで meta から設定。空なら包まない)
local body_style = nil

-- 原稿の画像を出現順に蓄積する (後処理のネイティブ SVG 埋込が件数・対応付けに使う)。
-- 生 Markdown 正規表現はキャプション内の角括弧・引用・参照形式画像で取りこぼし、件数不一致で
-- ビルドを中止させてしまう。pandoc AST から拾えば正確に数えられる。
local collected_images = {}

--- 文書順の i 番目の画像が .textbox Div の中にあるかを判定する
---
--- なぜ必要か: Pass 1 の Image ハンドラは AST 全体を歩くため「テキストボックス内かどうか」の
--- 文脈を持たない。それだけでは画像マニフェストが本文の図もフロート図表 (.textbox) 内の図も
--- 区別なく並べてしまう。一方 package の strip_inline_figures は _in_textbox で textbox 内図を
--- 温存するので、両者が食い違うと図番号が 3 系統に分裂する
--- (本文キャプション / [Figure N about here] の目印 / figures/FigureN のファイル)。
---
--- 本関数は Pass 1 と同じ文書順で読み取り専用に走査し、textbox 内画像の index を集合で返す。
--- .textbox は Div なので Div のみ手で再帰し、それ以外の入れ子 (段落・表・リスト内の inline) は
--- pandoc.walk_block に任せる。
--- 既知の制限: 表セルの中に .textbox Div を置いた場合は継承値で判定する (実用上そのような
--- 構成は取らない。.textbox は最上位に置くフロート図表として使う前提である)。
local function scan_textbox_images(blocks, in_tb, state)
  for _, block in ipairs(blocks) do
    if block.t == "Div" then
      local tb = in_tb or block.classes:includes("textbox")
      scan_textbox_images(block.content, tb, state)
    elseif block.t == "BlockQuote" then
      scan_textbox_images(block.content, in_tb, state)
    elseif block.t == "BulletList" or block.t == "OrderedList" then
      for _, item in ipairs(block.content) do
        scan_textbox_images(item, in_tb, state)
      end
    else
      -- Para / Plain / Header / Table / LineBlock 等: 配下の Image を文書順に数える
      pandoc.walk_block(block, {
        Image = function(_)
          state.n = state.n + 1
          if in_tb then state.tb[state.n] = true end
        end
      })
    end
  end
end

-- 相互再帰のための前方宣言
local process_blocks

--- .textbox Div: 中身を start/end マーカーで挟む
local function process_textbox(div)
  local attrs = div.attributes
  local width = to_emu(attrs["width"] or "0")
  local height = to_emu(attrs["height"] or "0")
  local pos_x = to_emu(attrs["pos-x"] or "0pt")
  local pos_y = to_emu(attrs["pos-y"] or "0pt")
  local anchor_h = attrs["anchor-h"] or "page"
  local anchor_v = attrs["anchor-v"] or "page"
  local wrap = attrs["wrap"] or "tight"
  local behind = attrs["behind"] or "false"
  local valign = attrs["valign"] or "top"
  local page = attrs["page"]  -- 任意 (未指定なら nil)

  local params = string.format(
    "TEXTBOX_START:width=%d;height=%d;pos-x=%d;pos-y=%d;anchor-h=%s;anchor-v=%s;wrap=%s;behind=%s;valign=%s",
    width, height, pos_x, pos_y, anchor_h, anchor_v, wrap, behind, valign)
  if page then
    params = params .. ";page=" .. page
  end

  local result = pandoc.List()
  result:insert(textbox_marker(params))
  -- 中身は通常どおり処理 (本文 Para 包み等も適用)
  local inner = process_blocks(div.content)
  result:extend(inner)
  result:insert(textbox_marker("TEXTBOX_END"))
  return result
end

--- ブロック列を再帰処理:
---   素の Para は (body_style があれば) その custom-style Div で包む
---   .textbox → マーカー、.grid → GRID_TABLE マーカー + 再帰
---   custom-style 付き Div はサブツリーごと温存、それ以外の Div は子へ再帰
process_blocks = function(blocks)
  local result = pandoc.List()
  for _, block in ipairs(blocks) do
    if block.t == "Para" then
      if body_style and body_style ~= "" then
        result:insert(pandoc.Div(block, pandoc.Attr("", {}, {{"custom-style", body_style}})))
      else
        result:insert(block)
      end
    elseif block.t == "Div" then
      if block.classes:includes("textbox") then
        result:extend(process_textbox(block))
      elseif block.classes:includes("grid") then
        -- .grid Div — 直後の表を全罫線化するマーカーを置く
        result:insert(textbox_marker("GRID_TABLE"))
        local inner = process_blocks(block.content)
        result:extend(inner)
      elseif has_custom_style(block) then
        -- 既に custom-style 付き — サブツリーごと温存 (二重包みしない)
        result:insert(block)
      else
        -- custom-style 無し — 子へ再帰
        block.content = process_blocks(block.content)
        result:insert(block)
      end
    else
      -- Header / Table / CodeBlock / List 等はそのまま通す
      result:insert(block)
    end
  end
  return result
end

return {
  -- Pass 1: 画像を出現順に記録し、SVG パスを *.svg.png へ書換 (pandoc 段は PNG を参照)
  { Image = function(img)
      -- 書換前の原稿パス・キャプションを記録
      collected_images[#collected_images + 1] = {
        src = img.src,
        caption = pandoc.utils.stringify(img.caption or {}),
      }
      if img.src:match("%.svg$") then
        img.src = img.src .. ".png"
      end
      return img
    end
  },
  -- Pass 2: メタから body-style を読み、ブロックを処理する。画像マニフェストを書き出す
  { Pandoc = function(doc)
      local bs = doc.meta["body-style"]
      if bs then
        body_style = pandoc.utils.stringify(bs)
      end
      -- .textbox 内画像の index を先に確定する (process_blocks が textbox を
      -- マーカー段落へ展開する前でなければ Div 構造を追えないため)
      local tbstate = { n = 0, tb = {} }
      scan_textbox_images(doc.blocks, false, tbstate)

      doc.blocks = process_blocks(doc.blocks)
      -- 画像マニフェスト (src <TAB> caption <TAB> in_textbox) を出力。image-manifest メタ指定時のみ。
      -- 後処理 postprocess.py がこれを読み、件数照合と埋込対象 SVG の解決に使う。
      -- 第 3 列 in_textbox (1|0) は package の export_figures が
      -- テキストボックス内図を分離対象から外すために使う。
      -- 読み手は split("\t") で列を全部割って必要な列を取る (caption 内のタブは下で空白へ置換)。
      -- postprocess.py は caption (2 列目) も読むので、split("\t", 1) で割ると 2 列目に 3 列目が混入し、
      -- キャプション照合が常に外れる。
      local mf = doc.meta["image-manifest"]
      if mf then
        local path = pandoc.utils.stringify(mf)
        local fh = io.open(path, "w")
        if fh then
          for i, im in ipairs(collected_images) do
            local cap = im.caption:gsub("[\t\r\n]", " ")
            local in_tb = tbstate.tb[i] and "1" or "0"
            fh:write(im.src .. "\t" .. cap .. "\t" .. in_tb .. "\n")
          end
          fh:close()
        else
          io.stderr:write("警告: 画像マニフェストを書けません: " .. path .. "\n")
        end
      end
      return doc
    end
  },
}
