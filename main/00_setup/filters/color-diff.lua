-- color-diff.lua: 差分 span を文字スタイルへマップする (差分経路 step03 専用)
--
-- 構造保持 AST 差分 (main/step03_diff/) が付けた以下の Span を、docx の文字スタイル参照へ変換する:
--   [..]{.diff-add} → custom-style="DiffAdd" (青 #2E74B5)
--   [..]{.diff-del} → custom-style="DiffDel" (赤 #C00000 + 取消線)
--
-- 【重要】生 OOXML run は生成しない (docs/architecture.md §2.0 / §2.3、
-- docs/design-fullarea-diff.md §4)。理由:
--   - custom-style="DiffAdd" は pandoc docx ライタが <w:rStyle w:val="DiffAdd"/> を出すだけで、色そのものは
--     持たない。色の実体 (DiffAdd 青 / DiffDel 赤+取消線) は差分後処理 (lxml) が生成 docx の word/styles.xml へ
--     **冪等注入**する。これにより雑誌提供テンプレ (2 スタイルを持たない) でも差分色が出る。
--   - 色は run プロパティ (w:rStyle) として乗るため、postprocess.py の wrap_textboxes() が run を textbox へコピーする際にも
--     そのまま運ばれる → テキストボックス内セルの差分も色付きになる (先行プロジェクトの未解決点を解消)。
--   - 生インライン OOXML (`...`{=openxml}) は文脈により docx を壊す既知問題 (jgm/pandoc #5094/#6933) があり使わない。
--
-- Cite / 相互参照 / 数式は差分エンジン側で要素のまま温存されており、本フィルタは触らない。
-- docx 出力時のみ有効。フィルタ適用順は crossref → generic-style → citeproc → color-diff (最後)。

if FORMAT ~= "docx" then
  return {}
end

return {
  Span = function(el)
    if el.classes:includes("diff-add") then
      el.attributes["custom-style"] = "DiffAdd"
      el.classes = el.classes:filter(function(c) return c ~= "diff-add" end)
      return el
    elseif el.classes:includes("diff-del") then
      el.attributes["custom-style"] = "DiffDel"
      el.classes = el.classes:filter(function(c) return c ~= "diff-del" end)
      return el
    end
  end,
}
