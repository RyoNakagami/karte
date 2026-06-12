# karte — 使い方

`karte` はリポジトリごとの個人用 TODO／チケット管理ツールです．チケットは
リポジトリルートの `.karte/tickets.json` に人間が読める素の JSON 配列として
保存され，`.karte/` は `.git/info/exclude` に追加されるため，個人用のまま
コミットされることはありません．

> English version: [how-to-use.md](how-to-use.md)

## インストール

```bash
uv tool install karte          # 公開パッケージから
# またはローカルのチェックアウトから:
uv tool install --editable .
```

アップグレードは `uv tool upgrade karte`，アンインストールは
`uv tool uninstall karte`．インストール済みバージョンは
`karte --version`（または `-V`）で確認できます．

## はじめに

対象の git リポジトリ内で一度だけ実行します:

```bash
karte init
```

これで `.karte/tickets.json`（空の JSON 配列）が作成され，`.karte/` が
`.git/info/exclude` に追加されます．チケットが `git status` に現れたり
コミットされたりすることはありません．他のすべてのコマンドは `init`
実行済みであることが前提です．

## 日常のワークフロー

```bash
# チケットを作成
karte add "Fix auth bug" -d "token refresh fails" -p high \
     -f "src/auth.py,src/token.py" -t backend --end 2026-06-10

# 未完了チケットを一覧（done はデフォルトで非表示）
karte list

# 着手する（status=doing になり start_at が記録される）
karte start 1

# 詳細を確認
karte show 1

# 完了にする
karte done 1
```

## コマンド

### `karte add TITLE`

チケットを作成します．オプションはすべて省略可能です:

| オプション | 意味 |
|---|---|
| `-d, --desc TEXT` | 説明文． |
| `-s, --status` | `todo` \| `doing` \| `done`（デフォルト `todo`）． |
| `-p, --priority` | `low` \| `mid` \| `high`（デフォルト `mid`）． |
| `--start DATE` | 開始日．`YYYY-MM-DD` または ISO 8601． |
| `--end DATE` | 期限．同じ形式． |
| `-f, --files` | 関連ファイルパス（カンマ区切り）． |
| `-t, --tags` | タグ（カンマ区切り）． |
| `--set key=value` | カスタムフィールド（複数指定可．後述）． |

### `karte list`

優先度→ID 順のテーブル表示．done のチケットは明示しない限り表示されません:

```bash
karte list                # 未完了チケットのみ
karte list --all          # done も含める
karte list -s doing       # ステータスで絞り込み（done を見るなら `-s done`）
karte list -t backend     # タグで絞り込み
```

### `karte show ID`

1件のチケットの全詳細を表示します．カスタムフィールド（型つき）と説明文も
含まれます．

### `karte update ID`

チケットの部分更新．渡したオプションだけが変更されます:

```bash
karte update 1 -s done --desc "fixed in #42"
karte update 1 --end 2026-07-01 -p high
karte update 1 -t "backend,urgent"        # 注意: タグリスト全体が置き換わる
```

`add` と同じオプションに加えて `--title` が使えます．`--files` と `--tags`
は既存リストへの追記ではなく**全体の置き換え**です．

### `karte start ID` / `karte done ID`

ショートカットです．`start` は `status=doing` にし，未設定なら `start_at`
を記録します．`done` は `status=done` にします．

### `karte delete ID`

確認プロンプトのあとチケットを削除します．スクリプトから使う場合は
`-y` / `--yes` でプロンプトをスキップできます．

## カスタムフィールド（プロジェクトごとのスキーマ）

リポジトリごとに `.karte/schema.json` を手書きで編集して，独自の型つき
フィールドを定義できます．karte はこのファイルを読むだけで，書き換える
スキーマ系コマンドはありません．組み込みフィールド名の再定義はできません．

```json
{
  "fields": [
    {"name": "assignee", "type": "str"},
    {"name": "estimate", "type": "float", "default": 0},
    {"name": "sprint",   "type": "int", "required": true},
    {"name": "blocked",  "type": "bool", "default": false},
    {"name": "kind",     "type": "enum", "choices": ["bug","feat","chore"], "default": "feat"}
  ]
}
```

型: `str`, `int`, `float`, `bool`, `date`, `enum`．フィールドごとのキー:
`name` と `type`（必須），`required`（デフォルト false），`default`，
`choices`（`enum` では必須）．

```bash
karte schema                                  # 読み込まれたスキーマを表示
karte add "Fix login" --set sprint=12 --set assignee=alice --set kind=bug
karte update 1 --set blocked=true             # 検証・型変換される
```

値は `add`／`update` 時に型チェックされます．必須フィールドは指定（または
デフォルト）が必要で，enum は `choices` に一致しなければならず，不正な型は
拒否されます．カスタムフィールドは `karte query` のカラムとしても現れます．

## クエリ（DuckDB SQL）

SQL でチケットを検索できます．全チケットはテーブル `tickets` として公開され，
カラムは `id, title, description, status, priority, created_at, updated_at,
start_at, end_at, related_files[], tags[]` にカスタムフィールドを加えたもの
です．`related_files` と `tags` は DuckDB のリスト型です．

```bash
# フル SQL
karte query "SELECT id, title FROM tickets WHERE status='todo'"
karte query "SELECT status, count(*) AS n FROM tickets GROUP BY status"

# タグ／ファイル検索（リスト型）
karte query "SELECT * FROM tickets WHERE list_contains(tags, 'backend')"
karte query "SELECT id,title FROM tickets \
             WHERE len(list_filter(related_files, x -> x LIKE '%auth%')) > 0"

# 日付比較（文字列は TIMESTAMP として推論される）
karte query "SELECT id,title,end_at FROM tickets WHERE end_at < '2026-07-01'"

# ショートハンド: -w/-o/-l が SELECT * FROM tickets ... を組み立てる
karte query -w "priority='high'" -o "end_at" -l 10

karte query -w "id=1" --raw          # タブ区切り，スクリプト向け
```

フル SQL 文字列か，`-w/--where`・`-o/--order`・`-l/--limit` の
ショートハンドの**どちらか一方**だけを渡してください（併用は不可）．
`--raw` はリッチテーブルの代わりにタブ区切りの素のテキストを出力するので，
他ツールへのパイプに向いています．

## データファイルと手編集

`.karte/tickets.json` が唯一の正であり，インデントされた JSON 配列として
直接開いて編集できます．手編集は次のコマンド実行時（`query` 含む）に
反映されます．チケットのフィールド:

`id`, `title`, `description`, `status` (todo|doing|done),
`priority` (low|mid|high), `created_at`, `updated_at`, `start_at`, `end_at`,
`related_files`（リスト）, `tags`（リスト）．

日付は `YYYY-MM-DD` またはフル ISO 8601 を受け付けます．全体の構成は
[ARCHITECTURE.md](ARCHITECTURE.md) を参照してください．
