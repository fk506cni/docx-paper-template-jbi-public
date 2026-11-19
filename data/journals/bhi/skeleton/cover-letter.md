<!--
data/journals/bhi/skeleton/cover-letter.md — BHI 用カバーレター雛形

BHI の規定 (docs/journal-bhi.md §8) がカバーレターに含めるよう推奨する 4 点 (規定は "encouraged"):
  1. なぜ本稿が BioHealth Informatics に掲載されるべきか
  2. 雑誌ポリシーに関わる論点があればその説明
  3. 潜在的な競合利益の申告
  4. 未発表かつ他誌へ同時投稿していないことの確認
下の見出しコメントはその 4 点への対応を示す。提出時にコメントは残しても消してもよい
(pandoc は HTML コメントを docx に出力しない)。

使い方: cp data/journals/bhi/skeleton/cover-letter.md src/cover-letter.md
        bash scripts/build.sh --journal bhi --article-type original   # cover-letter.docx も同時に出る

注: build.sh は main.md と同じ reference.docx で変換するが、BHI では profile.yaml の
    line_numbers_scope: manuscript により、カバーレターからは行番号を外す (ページ番号は残る)。

【本文は custom-style Div を使わない素の Markdown でよい】(差分対象は原稿本体だけでよいため)。
-->

<<2026-00-00>>

To the Editor-in-Chief\
BioHealth Informatics

Dear Editor,

We are pleased to submit our manuscript entitled **"<<Title of the Manuscript>>"** for
consideration as an <<Original Article>> in BioHealth Informatics.

<!-- (1) なぜ本稿が BHI に掲載されるべきか -->

<<本稿が扱う問題と、本誌の読者にとっての意義を 3〜5 文で。何が新しいか、どの読者層に
届くか、本誌のスコープ (医療情報学) のどこに位置づくかを具体的に書く。>>

<!-- (2) 雑誌ポリシーに関わる論点 -->

<<該当する場合のみ記載する。例: 既発表の学会抄録との関係、二次利用データの許諾、
先行公開 (preprint) の有無、報告ガイドライン (STROBE / PRISMA / STARE-HI 等) への準拠、
補足資料の内容。該当が無ければ「Not applicable」ではなく、この段落ごと削除してよい。>>

<!-- (3) 潜在的な競合利益の申告 -->

<<競合利益の有無。無い場合:
The authors declare that they have no competing interests related to this work.>>

<!-- (4) 未発表かつ他誌へ同時投稿していないことの確認 -->

This manuscript is original, has not been published previously, and is not under
consideration for publication elsewhere. All authors have read and approved the submitted
version and agree to its submission to BioHealth Informatics.

<!-- 提出書類 (LTP/COI Forms) は COI Disclosure Form・License to Publish とも 1 通で、
     corresponding author が全著者を代表して記入し PDF で提出する (COI は For Authors の Competing interests、
     LTP は様式の記述による)。詳細は data/journals/bhi/profile.yaml の submission.forms と
     docs/journal-bhi.md §4.1 を参照。 -->

We look forward to hearing from you.

Sincerely,

<<Given-name Family-name>>, on behalf of all authors\
<<Department>>, <<Institution>>\
<<City>>, <<Country>>\
E-mail: <<name@example.org>>
