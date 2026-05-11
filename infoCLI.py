import urllib.request
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import unicodedata
import time
from google import genai
import os

# --- 【設定：AIの鍵（金庫から取り出す）】 ---
# 直接書かずに os.environ.get を使うのがプロの鉄則
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    print("❌ エラー: 環境変数 GOOGLE_API_KEY が見つかりません。")
    # キーがないと動かないので、ここで止める
    exit()

client = genai.Client(api_key=GOOGLE_API_KEY)

# --- 【部品1：分析担当（AIAnalyzer）】 ---
class AIAnalyzer:
    def __init__(self, api_key):
        # メインはPro、予備はFlashという「二段構え」
        self.pro_model = 'gemini-3.1-pro-preview'
        self.flash_model = 'gemini-2.5-flash'
        self.client = genai.Client(api_key=api_key)

    def analyze(self, raw_text):
        """ 司令塔：まずはProに頼み、ダメならFlashに切り替える """
        try:
            # 第一志望：Pro
            return self._call_gemini(self.pro_model, raw_text)
        except Exception as e:
            # もし「429（使いすぎ）」エラーが出たら...
            if "429" in str(e):
                print(f"\n⚠️ {self.pro_model}の無料枠の制限に達しました。")
                print(f" 予備の {self.flash_model} に切り替えます。")
                # 第二志望：Flashで即リトライ
                try:
                    return self._call_gemini(self.flash_model, raw_text)
                except Exception as e2:
                    return f"❌ 予備モデルも失敗: {e2}"
            
            # それ以外のエラー（503混雑など）はそのまま返す
            return f"❌ 解析失敗: {e}"

    def _call_gemini(self, model_name, raw_text):
        """ 実行部：実際にAIにプロンプトを投げる（共通処理） """
        prompt = f"""
        あなたは「情報理工学部の優秀な学生」として、このニュースを分析してください。
        
        【分析の掟】
        1. AI臭い「〜です・ます」の羅列は禁止。
        2. 専門用語を使いつつ、自分の言葉で試行錯誤感のある考察を入れること。
        3. 技術的な背景や、経済的なインパクトをエンジニア目線で深掘りすること。

        【構成】
        ■ 数行で把握
        ■ 技術・経済的なエッセンス
        ■ 学生としてどう活かせるか

        記事原文: 
        {raw_text[:5000]}
        """
        
        response = self.client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        return response.text

# --- 【部品2：調達担当（NewsFetcher）】 ---
class NewsFetcher:
    def fetch_rss_root(self, url):
        """RSSを取得してXMLのルートを返す"""
        try:
            with urllib.request.urlopen(url) as response:
                return ET.fromstring(response.read())
        except Exception as e:
            print(f"❌ RSS取得失敗: {e}")
            return None

    def scrape_article(self, url):
        """URLから本文を抽出する"""
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        article_tag = soup.find('article')
        return article_tag.get_text() if article_tag else soup.get_text()

# --- 【部品3：現場監督（CLIController）】 ---
class CLIController:
    def __init__(self, api_key):
        self.fetcher = NewsFetcher()
        self.analyzer = AIAnalyzer(api_key)
        self.rss_map = {
            '1': ('📰 総合', 'https://news.yahoo.co.jp/rss/topics/top-picks.xml'),
            '2': ('📊 経済', 'https://news.yahoo.co.jp/rss/topics/business.xml'),
            '3': ('💻 IT・科学', 'https://news.yahoo.co.jp/rss/topics/it.xml')
        }

    def run(self):
        while True: # 【親ループ】カテゴリ選択
            print("\n" + "="*50)
            print("📰 InfoCLI v2.0: The Intelligence System")
            print("="*50)
            print("【カテゴリを選択してください】")
            for k, v in self.rss_map.items():
                print(f"[{k}] {v[0]}")
            
            cat_choice = input("\n番号を選択 (qで終了): ").strip()
            if cat_choice.lower() == 'q': break
            if cat_choice not in self.rss_map:
                print("❌ 正しい番号を入力してください")
                continue

            label, url = self.rss_map[cat_choice]
            print(f"\n✨ {label}モード起動")
            root = self.fetcher.fetch_rss_root(url)
            if root is None: continue

            self.search_loop(root) # 【子ループ】へ移動

    def search_loop(self, root):
        while True: # 【子ループ】キーワード検索・記事選択
            print("\n" + "-"*40)
            keyword_raw = input("検索キーワード [Enterで最新表示 / bで戻る / qで終了]: ").strip()
            keyword = unicodedata.normalize('NFKC', keyword_raw).lower()

            if keyword == 'q': exit() # プログラム完全終了
            if keyword == 'b': break # 親ループ（カテゴリ選択）に戻る

            # 記事リストの作成
            news_list = []
            for item in root.findall('.//item'):
                title = item.find('title').text
                link = item.find('link').text
                # キーワードが空、またはタイトルに含まれる場合にリスト追加
                if not keyword or keyword in title.lower():
                    news_list.append({'title': title, 'link': link})

            if not news_list:
                print(f"❌ 「{keyword}」に一致する記事はありません。")
                continue

            # リスト表示（最大10件）
            print(f"\n--- 記事一覧 ({'最新' if not keyword else keyword}) ---")
            for i, news in enumerate(news_list[:10], 1):
                print(f"[{i}] {news['title']}")

            self.article_select_loop(news_list[:10])

    def article_select_loop(self, news_list):
        while True:
            choice = input(f"\n記事を選択 (1-{len(news_list)}) / [Enterで検索に戻る]: ").strip()
            if not choice: break # 検索ループに戻る

            if not choice.isdigit() or not (1 <= int(choice) <= len(news_list)):
                print("❌ 有効な番号を入力してください")
                continue

            target = news_list[int(choice) - 1]
            print(f"\n🧠 AI解析中: {target['title']}")
            
            raw_text = self.fetcher.scrape_article(target['link'])
            report = self.analyzer.analyze(raw_text)
            
            print("\n" + "="*50)
            print(report)
            print("="*50)
            print(f"🔗 元記事: {target['link']}")
            break # 1つ解析したら検索ループに戻る

# --- 【メイン処理】 ---ha
if __name__ == "__main__":
    if not GOOGLE_API_KEY:
        print("❌ エラー: 環境変数が設定されていません")
    else:
        app = CLIController(GOOGLE_API_KEY)
        app.run()
            