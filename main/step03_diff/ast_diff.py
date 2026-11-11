#!/usr/bin/env python3
"""ast_diff.py — 構造保持型 二層 AST 差分エンジン (Step 03 diff の中核)。

docs/architecture.md §2.3 / docs/design-fullarea-diff.md。pandiff は使わない。旧版・新版の pandoc AST
(panflute Doc) を突き合わせ、構造 (custom-style Div / native Table / .textbox Div /
raw openxml / Figure) を一切壊さず、変更語句だけを Span (.diff-add / .diff-del) で包んだ
1 つのマージ Doc を返す。色付けは色実体ではなく Span のクラスのみ付与し、後段の
color-diff.lua が custom-style="DiffAdd"/"DiffDel" 文字スタイルへ写像する。

二層アルゴリズム:
  レベル1   : ブロック列を difflib (= LCS 系) で整列。`equal` は新版を温存。
  レベル1.5 : `replace` 区間で旧/新ブロックを類似度 (しきい値 0.5) ・同種別で対応付ける
              (層1→層2 の橋渡し。これが無いと 1 語修正の段落が段落まるごと赤青になる)。
  レベル2   : 対応した葉ブロック内のインラインを語単位で差分し変更語を Span で包む。
              Cite / 相互参照 / 数式 / Image は不透明トークンとして要素のまま温存する。
  コンテナ  : Div / Table / リスト / Figure / Caption は型のついた木をたどって再帰する。

このモジュールは I/O を持たず純粋に Doc → Doc を行う (テスト容易性のため)。CLI は
2 つの pandoc JSON を読み、マージ JSON を stdout に書く。実運用は diff_docx.py が
diff_documents() を直接呼ぶ。
"""

import copy
import difflib
import re
import sys

import panflute as pf

# レベル1.5 で「同一ブロックの改稿」とみなす類似度しきい値 (docs/architecture.md §2.3 / docs/design-fullarea-diff.md §3 の「レベル1.5」)
SIMILARITY_THRESHOLD = 0.5

# 差分 span のクラス名 (color-diff.lua がこれを custom-style 文字スタイルへ写像する)
ADD = "diff-add"
DEL = "diff-del"

# 語差分でインラインをまたぐ「空白」とみなすトークン
_WS_TAGS = {"Space", "SoftBreak", "LineBreak"}


# =====================================================================
# 正規化・署名・類似度
# =====================================================================

def _normalize(text):
    """署名・類似度比較用にテキストを正規化する (小文字化・空白畳み込み)。"""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _type_key(block):
    """ブロックの「種別キー」。同種別判定 (レベル1.5 の対応付け制約) に使う。

    Div は custom-style とクラスを、Header はレベルを種別に含める。これにより
    Title Div と Author Div、見出しレベル違いが誤って対応付けられない。
    """
    t = block.tag
    if t == "Div":
        cs = (block.attributes or {}).get("custom-style")
        return f"Div:{cs}:{','.join(block.classes)}"
    if t == "Header":
        return f"Header:{block.level}"
    return t


def _full_sig(block):
    """レベル1 の LCS 整列に使う署名 (種別キー + 正規化テキスト)。"""
    return _type_key(block) + "\x00" + _normalize(pf.stringify(block))


def _word_tokens(el):
    """要素から比較用の語トークンを集める。`Str` を語に割って集めるので、表のセルや
    リスト項目が「区切り無しの 1 トークン」に潰れない。

    `pf.stringify` はセルを区切り無しで連結する (例: `| A | B |/| 1 | 2 |` → `'AB12'`)。
    これを `.split()` すると 1 トークンになり、`_similarity` が単語・数値セルの表で常に 0 を返す。
    その結果、変更された表がペアにならず表全体が「旧=全赤/新=全青」に二重化する。"""
    words = []

    def _collect(e, doc=None):
        if isinstance(e, pf.Str):
            words.extend(_normalize(e.text).split())
        return e

    el.walk(_collect)
    return words


def _similarity(a, b):
    """2 ブロックのテキスト類似度 (語列の difflib 比)。0..1。

    語列は `_word_tokens` で集める (stringify 連結ではセル境界が消えるため)。"""
    ta = _word_tokens(a)
    tb = _word_tokens(b)
    if not ta and not tb:
        return 1.0
    return difflib.SequenceMatcher(None, ta, tb, autojunk=False).ratio()


# =====================================================================
# レベル2: インライン語差分
# =====================================================================

def _tokenize_inlines(inlines):
    """インライン列を (key, element) トークン列へ展開する。

    pandoc は地の文を Str (語) と Space に既に分割しているので、要素単位のトークン化で
    語単位差分になる。Emph/Strong/Cite/Math/Link/Image/Code 等の複合・不透明インラインは
    1 つの不透明トークンとして扱う (要素内部だけの変更は要素まるごとの置換になる。docs/design-fullarea-diff.md §6)。
    """
    tokens = []
    for el in inlines:
        if el.tag == "Str":
            tokens.append((el.text, el))
        elif el.tag in _WS_TAGS:
            tokens.append((" ", el))  # 改行も空白扱いで一致させる (描画は元要素を温存)
        else:
            # 不透明トークン: 種別 + 文字列化で同一物だけが一致する
            tokens.append(("\x00" + el.tag + "\x00" + pf.stringify(el), el))
    return tokens


def _is_ws(el):
    return el.tag in _WS_TAGS


def _emit_group(elements, cls, out):
    """変更されたインライン群を Span(cls) で包んで out へ追加する。

    両端の空白トークンは Span の外へ出し、色付き run が無意味な空白で広がるのを防ぐ。
    語が 1 つも無い (空白のみ) 群は包まずそのまま出す。
    """
    lead, core, trail = [], list(elements), []
    while core and _is_ws(core[0]):
        lead.append(core.pop(0))
    while core and _is_ws(core[-1]):
        trail.insert(0, core.pop())
    out.extend(lead)
    if core:
        out.append(pf.Span(*core, classes=[cls]))
    out.extend(trail)


def _inline_diff(old_inlines, new_inlines):
    """対応した葉ブロックのインラインを語単位差分し、変更語を Span で包んだ列を返す。"""
    old_t = _tokenize_inlines(old_inlines)
    new_t = _tokenize_inlines(new_inlines)
    sm = difflib.SequenceMatcher(None, [k for k, _ in old_t], [k for k, _ in new_t],
                                 autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out.extend(copy.deepcopy(e) for _, e in new_t[j1:j2])
        elif op == "insert":
            _emit_group([copy.deepcopy(e) for _, e in new_t[j1:j2]], ADD, out)
        elif op == "delete":
            _emit_group([copy.deepcopy(e) for _, e in old_t[i1:i2]], DEL, out)
        elif op == "replace":
            # latexdiff 流に「削除(旧)→追加(新)」の順で並べる
            _emit_group([copy.deepcopy(e) for _, e in old_t[i1:i2]], DEL, out)
            _emit_group([copy.deepcopy(e) for _, e in new_t[j1:j2]], ADD, out)
    return out


# =====================================================================
# 全体着色 (ブロック丸ごとの追加 / 削除)
# =====================================================================

def _wrap_all(inlines, cls):
    """葉ブロックのインライン全体を 1 つの Span(cls) で包む (空なら空リスト)。"""
    inlines = list(inlines)
    if not inlines:
        return []
    return [pf.Span(*inlines, classes=[cls])]


def _colorize(block, cls):
    """ブロック (とその子) のテキストを丸ごと cls で着色する。block は破壊的に変更される。

    追加ブロック (diff-add) / 削除ブロック (diff-del) の全文を一色にするために使う。
    画像・数式・引用などの不透明インラインは Span 内に温存される (要素は壊さない)。
    CodeBlock / RawBlock / HorizontalRule など run スタイルを乗せられない要素は素通し。
    """
    t = block.tag
    if t in ("Para", "Plain", "Header"):
        block.content = _wrap_all(block.content, cls)
        return block
    if t == "Figure":
        # キャプションを着色する。削除図 (DEL) は画像本体を残さず Div へ畳む:
        # 削除図のファイルは作業ツリーに無いことがあり (図前処理は新版基準)、画像を温存すると
        # pandoc が図を落とし、件数照合 (原稿画像数 != docx 図数) が差分生成を中止させる。
        # 追加図 (ADD) はファイルが作業ツリーに在るので画像を温存する。
        cap_blocks = ([_colorize(b, cls) for b in block.caption.content]
                      if block.caption is not None else [])
        if cls == DEL:
            return pf.Div(*cap_blocks, classes=["deleted-figure"])
        block.caption = pf.Caption(*cap_blocks)
        block.content = [_colorize(b, cls) for b in block.content]
        return block
    if t in ("Div", "BlockQuote", "Note"):
        block.content = [_colorize(b, cls) for b in block.content]
        return block
    if t == "Table":
        return _colorize_table(block, cls)
    if t in ("BulletList", "OrderedList"):
        # panflute は項目を ListItem オブジェクト (反復不可、中身は .content) で持つ。
        # 項目を [Block] とみなして `for b in item` と書くと TypeError で止まる
        items = [pf.ListItem(*[_colorize(b, cls) for b in item.content])
                 for item in block.content]
        if t == "OrderedList":
            return pf.OrderedList(*items, start=block.start, style=block.style,
                                  delimiter=block.delimiter)
        return pf.BulletList(*items)
    # 不透明 (CodeBlock / RawBlock / HorizontalRule / LineBlock 等) は素通し
    return block


def _colorize_table(tbl, cls):
    if tbl.caption is not None:
        tbl.caption = pf.Caption(*[_colorize(b, cls) for b in tbl.caption.content])
    for sec in (tbl.head, tbl.foot):
        if sec is None:
            continue
        for row in sec.content:
            for cell in row.content:
                cell.content = [_colorize(b, cls) for b in cell.content]
    for body in tbl.content:
        for row in body.content:
            for cell in row.content:
                cell.content = [_colorize(b, cls) for b in cell.content]
    return tbl


def _color_block(block, cls):
    """deepcopy してから丸ごと着色する (元 AST を汚さない)。"""
    return _colorize(copy.deepcopy(block), cls)


# =====================================================================
# コンテナ要素の再帰差分
# =====================================================================

def _diff_caption(old_cap, new_cap):
    old_blocks = list(old_cap.content) if old_cap is not None else []
    new_blocks = list(new_cap.content) if new_cap is not None else []
    return pf.Caption(*_diff_blocks(old_blocks, new_blocks))


def _diff_figure(old, new):
    """Figure: 画像本体 (新版) は温存し、キャプションだけを差分化する。"""
    fig = copy.deepcopy(new)
    fig.caption = _diff_caption(old.caption, new.caption)
    return fig


def _row_sig(row):
    return _normalize("\x1f".join(pf.stringify(c) for c in row.content))


def _diff_row_cells(old_row, new_row):
    """対応した行: セルを位置で対応付け、各セル内ブロックを再帰差分する。"""
    nr = copy.deepcopy(new_row)
    old_cells = list(old_row.content)
    new_cells = list(new_row.content)
    out_cells = []
    for ci, nc in enumerate(new_cells):
        if ci < len(old_cells):
            merged = _diff_blocks(list(old_cells[ci].content), list(nc.content))
            cell = copy.deepcopy(nc)
            cell.content = merged
            out_cells.append(cell)
        else:
            cell = copy.deepcopy(nc)
            cell.content = [_colorize(b, ADD) for b in cell.content]
            out_cells.append(cell)
    nr.content = out_cells
    return nr


def _colorize_row(row, cls):
    nr = copy.deepcopy(row)
    for cell in nr.content:
        cell.content = [_colorize(b, cls) for b in cell.content]
    return nr


def _diff_rows(old_rows, new_rows):
    """行列を整列して差分行列を返す。

    対応行はセル差分、追加行は全 add 着色、削除行は全 del 着色して新表の中に残す。
    """
    o_sig = [_row_sig(r) for r in old_rows]
    n_sig = [_row_sig(r) for r in new_rows]
    sm = difflib.SequenceMatcher(None, o_sig, n_sig, autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out.extend(copy.deepcopy(r) for r in new_rows[j1:j2])
        elif op == "insert":
            out.extend(_colorize_row(r, ADD) for r in new_rows[j1:j2])
        elif op == "delete":
            out.extend(_colorize_row(r, DEL) for r in old_rows[i1:i2])
        elif op == "replace":
            o = old_rows[i1:i2]
            n = new_rows[j1:j2]
            for k in range(max(len(o), len(n))):
                if k < len(o) and k < len(n):
                    out.append(_diff_row_cells(o[k], n[k]))
                elif k < len(n):
                    out.append(_colorize_row(n[k], ADD))
                else:
                    out.append(_colorize_row(o[k], DEL))
    return out


def _diff_table_section(old_sec, new_sec, _ctor):
    sec = copy.deepcopy(new_sec)
    old_rows = list(old_sec.content) if old_sec is not None else []
    sec.content = _diff_rows(old_rows, list(new_sec.content))
    return sec


def _diff_table_body(old_body, new_body):
    nb = copy.deepcopy(new_body)
    old_rows = list(old_body.content) if old_body is not None else []
    nb.content = _diff_rows(old_rows, list(new_body.content))
    return nb


def _diff_table(old, new):
    """Table: 新版の骨格 (colspec/identifier) を保ち、キャプション・各セルを差分化する。

    行は署名で整列し、セルは位置で対応付ける (colspan/rowspan を含む複雑表は曖昧。既知制限)。
    """
    tbl = copy.deepcopy(new)
    tbl.caption = _diff_caption(old.caption, new.caption)
    tbl.head = _diff_table_section(old.head, new.head, pf.TableHead)
    old_bodies = list(old.content)
    new_bodies = []
    for bi, nb in enumerate(new.content):
        ob = old_bodies[bi] if bi < len(old_bodies) else None
        new_bodies.append(_diff_table_body(ob, nb))
    tbl.content = new_bodies
    tbl.foot = _diff_table_section(old.foot, new.foot, pf.TableFoot)
    return tbl


def _item_sig(item):
    # item は panflute の ListItem (中身は .content)。反復できないので
    # `for b in item` ではなく `item.content` をたどる。
    return _normalize("\x1f".join(pf.stringify(b) for b in item.content))


def _diff_list(old, new):
    """BulletList / OrderedList: 項目を署名で整列し、対応項目を再帰差分する。

    panflute は項目を ListItem オブジェクトで持つ (中身は .content)。項目を [Block] とみなして
    `for b in item` / `list(item)` / `pf.BulletList(*[[Block]])` と書くと TypeError で止まる
    (リストの追加・削除・編集のすべてで)。各分岐は ListItem を作る。"""
    old_items = list(old.content)   # ListItem の並び
    new_items = list(new.content)
    sm = difflib.SequenceMatcher(None, [_item_sig(x) for x in old_items],
                                 [_item_sig(x) for x in new_items], autojunk=False)
    out_items = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out_items.extend(copy.deepcopy(it) for it in new_items[j1:j2])
        elif op == "insert":
            out_items.extend(pf.ListItem(*[_colorize(copy.deepcopy(b), ADD) for b in it.content])
                             for it in new_items[j1:j2])
        elif op == "delete":
            out_items.extend(pf.ListItem(*[_colorize(copy.deepcopy(b), DEL) for b in it.content])
                             for it in old_items[i1:i2])
        elif op == "replace":
            o = old_items[i1:i2]
            n = new_items[j1:j2]
            for k in range(max(len(o), len(n))):
                if k < len(o) and k < len(n):
                    out_items.append(pf.ListItem(*_diff_blocks(list(o[k].content), list(n[k].content))))
                elif k < len(n):
                    out_items.append(pf.ListItem(*[_colorize(copy.deepcopy(b), ADD) for b in n[k].content]))
                else:
                    out_items.append(pf.ListItem(*[_colorize(copy.deepcopy(b), DEL) for b in o[k].content]))
    if new.tag == "OrderedList":
        return pf.OrderedList(*out_items, start=new.start, style=new.style,
                              delimiter=new.delimiter)
    return pf.BulletList(*out_items)


# =====================================================================
# 対応ブロックの差分 (種別ごとに分岐)
# =====================================================================

def _diff_pair(old, new):
    """同種別で対応した 1 ブロックを差分化し、ブロックのリストを返す。"""
    t = new.tag
    if t in ("Para", "Plain"):
        ctor = pf.Para if t == "Para" else pf.Plain
        return [ctor(*_inline_diff(list(old.content), list(new.content)))]
    if t == "Header":
        inl = _inline_diff(list(old.content), list(new.content))
        return [pf.Header(*inl, level=new.level, identifier=new.identifier,
                          classes=list(new.classes), attributes=dict(new.attributes))]
    if t == "Div":
        merged = _diff_blocks(list(old.content), list(new.content))
        return [pf.Div(*merged, identifier=new.identifier, classes=list(new.classes),
                       attributes=dict(new.attributes))]
    if t == "BlockQuote":
        return [pf.BlockQuote(*_diff_blocks(list(old.content), list(new.content)))]
    if t == "Figure":
        return [_diff_figure(old, new)]
    if t == "Table":
        return [_diff_table(old, new)]
    if t in ("BulletList", "OrderedList"):
        return [_diff_list(old, new)]
    # その他 (CodeBlock / RawBlock / 数式 Para 等の不透明): 変化なしなら温存、変化ありなら del+add
    if _normalize(pf.stringify(old)) == _normalize(pf.stringify(new)):
        return [copy.deepcopy(new)]
    return [_color_block(old, DEL), _color_block(new, ADD)]


# =====================================================================
# レベル1 + レベル1.5: ブロック列の整列と replace 橋渡し
# =====================================================================

def _greedy_pairs(old_chunk, new_chunk):
    """replace 区間で同種別・類似度しきい値以上の旧/新ブロックを対応付ける。

    貪欲 (類似度降順) に 1 対 1 で割当て、最後に新順で旧インデックス単調増加を満たす対のみ
    残す (交差対は外し add/del へ倒す)。これで後段のマージ走査が順序破綻しない。
    """
    cands = []
    for nj, nb in enumerate(new_chunk):
        nk = _type_key(nb)
        for oi, ob in enumerate(old_chunk):
            if _type_key(ob) != nk:
                continue
            s = _similarity(ob, nb)
            if s >= SIMILARITY_THRESHOLD:
                cands.append((s, nj, oi))
    cands.sort(key=lambda x: (-x[0], x[1], x[2]))
    pair, used_o, used_n = {}, set(), set()
    for _s, nj, oi in cands:
        if nj in used_n or oi in used_o:
            continue
        pair[nj] = oi
        used_n.add(nj)
        used_o.add(oi)
    mono, last = {}, -1
    for nj in sorted(pair):
        if pair[nj] > last:
            mono[nj] = pair[nj]
            last = pair[nj]
    return mono


def _match_replace(old_chunk, new_chunk):
    """replace 区間: 対応付け (レベル1.5) → 対応対は差分、非対応は add/del 着色。

    対応対 (旧インデックス単調増加) をアンカーに旧/新を二ポインタでマージし、
    順序を保ったまま削除ブロック (赤) を新版の流れの中へ差し込む。
    """
    pairing = _greedy_pairs(old_chunk, new_chunk)
    matched_old = set(pairing.values())
    out = []
    oi = 0
    for nj in range(len(new_chunk)):
        if nj in pairing:
            anchor = pairing[nj]
            while oi < anchor:  # アンカー手前の未対応旧 = 削除
                if oi not in matched_old:
                    out.append(_color_block(old_chunk[oi], DEL))
                oi += 1
            out.extend(_diff_pair(old_chunk[anchor], new_chunk[nj]))
            oi = anchor + 1
        else:
            out.append(_color_block(new_chunk[nj], ADD))  # 対応なしの新 = 追加
    while oi < len(old_chunk):  # 末尾に残った未対応旧 = 削除
        if oi not in matched_old:
            out.append(_color_block(old_chunk[oi], DEL))
        oi += 1
    return out


def _diff_blocks(old_blocks, new_blocks):
    """ブロック列を整列し、マージしたブロック列 (構造温存 + 差分 span) を返す。"""
    o_keys = [_full_sig(b) for b in old_blocks]
    n_keys = [_full_sig(b) for b in new_blocks]
    sm = difflib.SequenceMatcher(None, o_keys, n_keys, autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out.extend(copy.deepcopy(b) for b in new_blocks[j1:j2])
        elif op == "insert":
            out.extend(_color_block(b, ADD) for b in new_blocks[j1:j2])
        elif op == "delete":
            out.extend(_color_block(b, DEL) for b in old_blocks[i1:i2])
        elif op == "replace":
            out.extend(_match_replace(old_blocks[i1:i2], new_blocks[j1:j2]))
    return out


# =====================================================================
# 公開 API
# =====================================================================

def diff_documents(old_doc, new_doc):
    """旧/新 panflute Doc を突き合わせ、マージ Doc を返す。

    マージ後 Doc は新版の Meta (crossref 接頭辞 / citeproc / lang 等) を採る。
    構造は温存され、変更語句のみ Span(.diff-add/.diff-del) で包まれる。
    """
    merged = copy.deepcopy(new_doc)
    merged.content = _diff_blocks(list(old_doc.content), list(new_doc.content))
    return merged


def main(argv=None):
    """CLI: 2 つの pandoc JSON (旧 新) を読み、マージ JSON を stdout へ。"""
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        sys.exit("usage: ast_diff.py OLD.json NEW.json  (マージ JSON を stdout へ出力)")
    with open(argv[0], encoding="utf-8") as f:
        old_doc = pf.load(f)
    with open(argv[1], encoding="utf-8") as f:
        new_doc = pf.load(f)
    merged = diff_documents(old_doc, new_doc)
    pf.dump(merged, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
